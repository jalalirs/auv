"""make-site's --raster reader, for a GeoTIFF in degrees: cut to the place's
square and decimated. The places module's own raster source (raster.py) reads
any raster in any coordinate system; this stays for make-site."""

from __future__ import annotations

import math

from ..grid import metres_per_degree


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
