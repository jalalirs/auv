"""A client's own data: a survey raster, an orthomosaic, in whatever
coordinate system it came in.

A client's multibeam grid or lidar DEM is rarely in degrees: Looe Key's SQUID-5
DEM is UTM 17N on NAVD88, a Saudi survey will be UTM 37N on some chart datum.
So the raster is reprojected onto the site's grid by GDAL, which a place's grid
can be handed to directly: its cells are evenly spaced in longitude and in
latitude (metres from the middle over a fixed metres-per-degree), which makes
it a plain EPSG:4326 raster. A survey finer than the grid is averaged into each
cell rather than sampled, because a 1 m survey read at 4 m points is a quarter
of the survey and all of its noise; one coarser is interpolated.

Heights or depths, in the survey's own vertical datum: say `depthsPositive`
when the numbers are depths, and fit the datum with `datum-fit` against
something measured (ICESat-2's photons are orthometric, as every satellite fit
here is) rather than assume it.
"""

from __future__ import annotations

import pathlib

import numpy as np

from ..grid import Grid, metres_per_degree
from ..layer import Layer, Provenance
from . import where


def grid_transform(grid: Grid):
    """The site's grid as an EPSG:4326 raster: its affine transform, rows
    north first as GDAL wants them."""
    from rasterio.transform import from_origin

    east, north = metres_per_degree(grid.latitude)
    dlon, dlat = grid.cell / east, grid.cell / north
    west, _, _, top = grid.bounds()
    # Cell centres sit on the bounds; the raster's edges are half a cell out.
    return from_origin(west - dlon / 2, top + dlat / 2, dlon, dlat)


def onto(grid: Grid, path: pathlib.Path, band: int = 1, average: bool | None = None) -> tuple[np.ndarray, dict]:
    """One band of a raster on the grid, rows south first; NaN where it has
    nothing. Returns the values and what the raster says about itself."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    n = grid.cells
    out = np.full((n, n), np.nan, dtype="float64")
    with rasterio.open(path) as src:
        native = abs(src.res[0])
        # Its pixel size in metres, near enough to choose how to resample.
        if src.crs and src.crs.is_geographic:
            native *= metres_per_degree(grid.latitude)[1]
        if average is None:
            average = native < grid.cell * 0.75
        reproject(source=rasterio.band(src, band), destination=out,
                  src_nodata=src.nodata, dst_nodata=np.nan,
                  dst_transform=grid_transform(grid), dst_crs="EPSG:4326",
                  resampling=Resampling.average if average else Resampling.bilinear)
        about = {"crs": src.crs.to_string() if src.crs else None, "pixelM": round(float(native), 3),
                 "bands": src.count, "resampled": "averaged into each cell" if average else "bilinear"}
    return out[::-1].copy(), about


class Raster:
    """A survey raster: GeoTIFF, ESRI ASCII grid, BAG, anything GDAL opens.
    `error` is chosen unless `uncertaintyBand` names a band that holds it (a
    BAG's second band, say); `depthsPositive` turns depths into heights."""

    name = "raster"
    gives = ("depth",)

    def __init__(self, file: str, path: str | None = None, error: float = 0.3, band: int = 1,
                 uncertaintyBand: int | None = None, depthsPositive: bool = False,  # noqa: N803
                 kind: str = "measured", citation: str = "", datum: str = "", licence: str = "",
                 name: str | None = None) -> None:
        self.file, self.path, self.error, self.band = file, path, float(error), int(band)
        self.uncertainty_band, self.depths_positive = uncertaintyBand, bool(depthsPositive)
        self.kind, self.citation, self.datum, self.licence = kind, citation, datum, licence
        if name:
            self.name = name

    def _file(self, cache) -> pathlib.Path:
        f = pathlib.Path(self.file).expanduser()
        return f if f.is_absolute() else where(self.path, cache) / f

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        f = self._file(cache)
        value, about = onto(grid, f, self.band)
        if self.depths_positive:
            value = -value
        if self.uncertainty_band:
            error, _ = onto(grid, f, int(self.uncertainty_band))
            error = np.where(np.isfinite(error), error, self.error)
            chosen = ""
        else:
            error = np.full(value.shape, self.error)
            chosen = f"; error {self.error:g} m, chosen"
        cited = Provenance(
            self.name, self.kind,
            (self.citation or f.name) + f" ({about['crs']}, {about['pixelM']:g} m pixels, {about['resampled']}"
            + (f"; vertical datum {self.datum}" if self.datum else "") + chosen + ")",
            self.licence, {"surveys": [{"name": f.name, "sampleMetres": about["pixelM"]}]})
        return [Layer.of(grid, "depth", value, error, cited)]


class Ortho:
    """An orthomosaic: its red, green and blue on the grid, as colour layers a
    model or the ground can take."""

    name = "ortho"
    gives = ("red", "green", "blue")

    def __init__(self, file: str, path: str | None = None, bands: list[int] | None = None,
                 citation: str = "", licence: str = "") -> None:
        self.file, self.path, self.bands = file, path, bands or [1, 2, 3]
        self.citation, self.licence = citation, licence

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        f = pathlib.Path(self.file).expanduser()
        f = f if f.is_absolute() else where(self.path, cache) / f
        out = []
        for colour, band in zip(("red", "green", "blue"), self.bands):
            value, about = onto(grid, f, band)
            out.append(Layer.of(grid, colour, value, np.nan,
                                Provenance(self.name, "measured",
                                           (self.citation or f.name) + f" ({about['crs']}, {about['pixelM']:g} m pixels)",
                                           self.licence)))
        return out
