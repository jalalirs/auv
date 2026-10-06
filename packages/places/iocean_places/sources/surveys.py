"""Bathymetry somebody surveyed: a mosaic of surveys, and a survey's own DEM.

- `Bathymetry` reads what tools/get-bathymetry wrote (`<name>.f32` and its
  note): NOAA NCEI's mosaic of every survey it holds, best first, or GMRT's
  global synthesis where NOAA has nothing. Onto a finer grid of the same
  square it is resampled by cubic spline, as tools/ground always did.
- `SurveyDem` reads a survey's own DEM GeoTIFF (USGS SQUID-5 at Looe Key, 1 m)
  and places it on the grid pixel for pixel, as tools/ground did: in its own
  datum, with its holes. `datum-fit` shifts it onto a reference layer and
  cleans it before fusion.
"""

from __future__ import annotations

import json

import numpy as np

from ..grid import Grid, metres_per_degree
from ..layer import Layer, Provenance
from . import fetched, note_of, where


class Bathymetry:
    name = "bathymetry"
    gives = ("depth",)

    def __init__(self, path: str | None = None, place: str | None = None, error: float = 1.0,
                 samples: int = 512, service: str = "auto", fetch: bool = True) -> None:
        self.path, self.place, self.error = path, place, float(error)
        self.samples, self.service, self.fetch = int(samples), service, bool(fetch)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        from scipy import ndimage

        folder = where(self.path, cache)
        name = self.place or folder.name
        if not (folder / f"{name}.json").is_file() and self.fetch:
            from ..fetch.bathymetry import main
            folder.mkdir(parents=True, exist_ok=True)
            fetched(self.name, main, [name, grid.latitude, grid.longitude, "--across", grid.across,
                                      "--samples", self.samples, "--from", self.service, "--into", folder])
        said = json.loads((folder / f"{name}.json").read_text())
        field = said["heightfield"]
        height = np.fromfile(folder / field["file"], dtype="<f4").reshape(field["rows"], field["columns"])
        centre = said["centre"]
        same_square = (abs(centre["latitude"] - grid.latitude) < 1e-9
                       and abs(centre["longitude"] - grid.longitude) < 1e-9
                       and abs(float(said["acrossMetres"]) - grid.across) < 1e-6)
        if same_square:
            n = grid.cells
            value = ndimage.zoom(height.astype(float), (n / height.shape[0], n / height.shape[1]), order=3)
        else:
            from .sentinel2 import _resampled
            value = _resampled(height, Grid(centre["latitude"], centre["longitude"], float(said["acrossMetres"]),
                                            height.shape[0]), grid)
        surveyed = bool(said.get("surveyed"))
        note = {**note_of(said), "surveys": said.get("surveys", [])}
        cited = Provenance(self.name, "measured" if surveyed else "derived",
                           f"{said.get('source', 'a bathymetry mosaic')}, {said.get('sampleMetres', '?')} m samples, "
                           f"{len(said.get('surveys', []))} surveys; error chosen", "public domain", note)
        return [Layer.of(grid, "depth", value, self.error, cited)]


class SurveyDem:
    name = "survey-dem"
    gives = ("depth",)

    def __init__(self, path: str | None = None, pattern: str = "usgs/*DEM_1m*.tif", error: float = 0.1,
                 citation: str = "") -> None:
        self.path, self.pattern, self.error, self.citation = path, pattern, float(error), citation

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        import rasterio
        from rasterio.warp import transform

        folder = where(self.path, cache)
        found = sorted(folder.glob(self.pattern))
        if not found:
            raise ValueError(f"no survey DEM matching {self.pattern} in {folder}")
        with rasterio.open(found[0]) as d:
            dem = d.read(1).astype(float)
            dem[dem == d.nodata] = np.nan
            pixel = float(d.res[0])
            xs, ys = transform(d.crs, "EPSG:4326", [d.bounds.left, d.bounds.right], [d.bounds.bottom, d.bounds.top])
        dem = dem[::-1]                                   # row 0 south
        east, north = metres_per_degree(grid.latitude)
        x0, y0 = (xs[0] - grid.longitude) * east, (ys[0] - grid.latitude) * north
        n = grid.cells
        # Each DEM pixel onto the nearest cell, as tools/ground placed it.
        yi = np.round((np.arange(dem.shape[0]) * pixel + y0) / grid.cell + (n - 1) / 2 * 1.0).astype(int)
        xi = np.round((np.arange(dem.shape[1]) * pixel + x0) / grid.cell + (n - 1) / 2 * 1.0).astype(int)
        if grid.cell == 1.0 and pixel == 1.0:
            yi = np.round(np.arange(dem.shape[0]) + y0 + grid.across / 2).astype(int)
            xi = np.round(np.arange(dem.shape[1]) + x0 + grid.across / 2).astype(int)
        oky, okx = (yi >= 0) & (yi < n), (xi >= 0) & (xi < n)
        placed = np.full((n, n), np.nan)
        placed[np.ix_(yi[oky], xi[okx])] = dem[np.ix_(oky, okx)]
        note = {"surveys": [{"name": found[0].name, "sampleMetres": pixel}]}
        cited = Provenance(self.name, "measured",
                           self.citation or f"{found[0].name}, a survey's own DEM at {pixel:g} m, in its own datum",
                           "public domain", note)
        return [Layer(grid, "depth", placed.astype("float32"), np.full((n, n), self.error, "float32"),
                      np.where(np.isfinite(placed), 0, Layer.NONE).astype("u1"), [cited])]
