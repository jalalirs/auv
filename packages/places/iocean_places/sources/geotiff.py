"""A raster somebody surveyed: a GeoTIFF of depths or heights.

The first source this module had, because it is the one every client has: a
multibeam grid, a lidar DEM or a chart exported to GeoTIFF. Read in degrees,
cut to the place's square and resampled onto its grid.
"""

from __future__ import annotations

import pathlib

from ..grid import Grid, metres_per_degree
from ..layer import Layer, Provenance


def read_patch(raster, centre, across, most):
    """The square of seabed we want, as heights in metres above the water."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds

    latitude, longitude = centre
    east, north = metres_per_degree(latitude)
    half_lon = (across / 2) / east
    half_lat = (across / 2) / north

    with rasterio.open(raster) as source:
        window = from_bounds(longitude - half_lon, latitude - half_lat,
                             longitude + half_lon, latitude + half_lat,
                             source.transform)
        height = source.read(1, window=window, masked=True).astype("float32")
        if height.size == 0:
            raise SystemExit("that centre is not inside this raster")

        # Decimated to something a renderer can hold. A metre of resolution over
        # a kilometre is a million points and most of them say what their
        # neighbours already said.
        step = max(1, int(math.ceil(max(height.shape) / most)))
        height = height[::step, ::step]

        # A masked cell is somewhere the survey did not reach. Filled with the
        # nearest thing known rather than left as a hole, because a hole in a
        # seabed is a place a vehicle falls through, and saying "no data" to
        # somebody flying a vehicle is not useful when the alternative is "the
        # bottom is about here".
        filled = np.ma.filled(height, np.nan)
        if np.isnan(filled).any():
            flat = filled.copy()
            for _ in range(6):
                blurred = np.nanmean(np.stack([
                    np.roll(flat, 1, 0), np.roll(flat, -1, 0),
                    np.roll(flat, 1, 1), np.roll(flat, -1, 1),
                ]), axis=0)
                flat = np.where(np.isnan(flat), blurred, flat)
            filled = np.nan_to_num(flat, nan=float(np.nanmin(filled)))

    # North is up in a raster and +y in the world, so the rows are flipped.
    return np.flipud(filled), step


class GeoTiff:
    """Depths from a GeoTIFF.

    `error` is the vertical error the survey states, in metres; `kind` is
    what the numbers are (measured for a survey, derived for a model's
    output). `negate` for a raster of depths rather than heights."""

    name = "geotiff"
    gives = ("depth",)

    def __init__(self, path: str, error: float = 0.5, kind: str = "measured",
                 citation: str = "", negate: bool = False) -> None:
        self.path, self.error, self.kind, self.citation, self.negate = path, float(error), kind, citation, negate

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        import numpy as np

        height, _ = read_patch(self.path, (grid.latitude, grid.longitude), grid.across, grid.cells)
        height = np.asarray(height, dtype="float32")
        if self.negate:
            height = -height
        if height.shape != (grid.cells, grid.cells):
            from scipy.ndimage import zoom
            height = zoom(height, (grid.cells / height.shape[0], grid.cells / height.shape[1]), order=1)
        return [Layer.of(grid, "depth", height, self.error,
                         Provenance(self.name, self.kind, self.citation or f"the raster {pathlib.Path(self.path).name}"))]
