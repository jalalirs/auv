"""Sentinel-2: the reef from space, as colour and as a claimed depth.

Two products, each read from what the fetching tools wrote:

- `Sentinel2Median` is the median of the clearest scenes' true colour
  (tools/reference, `sentinel_median_rgb.npy`). Three layers, red, green and
  blue, as the scene stored them (0 to 255), with the scenes cited.
- `Stumpf` is one scene's satellite-derived depth (tools/get-reef, `<name>.f32`):
  Stumpf's log-ratio scaled against the reef's own geomorphology, uncalibrated,
  and the land the near infrared saw. A claim of shape, not of metres: what
  it is worth is what a model fitted to measured depths makes of it.
"""

from __future__ import annotations

import json

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance
from . import fetched, note_of, where


def _cut_to(grid: Grid, bbox) -> bool:
    """Whether a raster was cut to exactly this square."""
    return bool(np.allclose(grid.bounds(), bbox, rtol=0.0, atol=1e-9))


def picture_on(grid: Grid, picture: np.ndarray, bbox) -> np.ndarray:
    """A raster whose row 0 is north, spanning `bbox` corner to corner, on the
    grid by nearest sample; NaN off its edge. A raster cut to the square is
    read by index, as the tools always read it, so the same cell is the same
    sample here and there."""
    m_rows, m_cols = picture.shape[:2]
    n = grid.cells
    if _cut_to(grid, bbox):
        rows = np.clip(np.round((1.0 - np.arange(n) / (n - 1)) * (m_rows - 1)).astype(int), 0, m_rows - 1)
        cols = np.clip(np.round(np.arange(n) / (n - 1) * (m_cols - 1)).astype(int), 0, m_cols - 1)
        return picture[rows][:, cols].astype(float)
    west, south, east, north = bbox
    lon, lat = grid.lonlat()
    u = (lon - west) / (east - west) * (m_cols - 1)
    v = (north - lat) / (north - south) * (m_rows - 1)
    on = (u >= -0.5) & (u <= m_cols - 0.5) & (v >= -0.5) & (v <= m_rows - 0.5)
    i = np.clip(np.round(v).astype(int), 0, m_rows - 1)
    j = np.clip(np.round(u).astype(int), 0, m_cols - 1)
    out = picture[i, j].astype(float)
    out[~on] = np.nan
    return out


class Sentinel2Median:
    name = "sentinel2-median"
    gives = ("red", "green", "blue")

    def __init__(self, path: str | None = None, file: str = "sentinel_median_rgb.npy",
                 note: str = "sentinel.json", scenes: int = 8, cloud: float = 8.0, fetch: bool = True,
                 until: str = "2030-01-01T00:00:00Z") -> None:
        self.path, self.file, self.note, self.until = path, file, note, until
        self.scenes, self.cloud, self.fetch = int(scenes), float(cloud), bool(fetch)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        folder = where(self.path, cache)
        if not (folder / self.file).is_file() and self.fetch:
            from ..fetch.sentinel_median import from_space
            folder.mkdir(parents=True, exist_ok=True)
            if from_space(folder, grid.bounds(), self.scenes, self.cloud, self.until) is None:
                raise ValueError(f"{self.name}: no clear Sentinel-2 scenes could be read over this square")
        rgb = np.load(folder / self.file)
        said = json.loads((folder / self.note).read_text())
        colour = picture_on(grid, rgb, said["bbox"])
        scenes = said.get("scenes", [])
        cited = Provenance(self.name, "measured",
                           f"median of {len(scenes)} Sentinel-2 L2A scenes "
                           f"({', '.join(s['date'] for s in scenes[:3])}{'...' if len(scenes) > 3 else ''}), "
                           "true colour, via Earth Search", "Copernicus open data")
        return [Layer.of(grid, band, colour[..., k], np.nan, cited) for k, band in enumerate(("red", "green", "blue"))]


class Stumpf:
    name = "sentinel2-stumpf"
    gives = ("depth", "land")

    def __init__(self, path: str | None = None, place: str | None = None, error: float = 10.0,
                 samples: int = 512, since: str = "2022-01-01T00:00:00Z", cloud: float = 3.0,
                 deep: float = 60.0, fetch: bool = True, until: str = "2030-01-01T00:00:00Z") -> None:
        self.path, self.place, self.error, self.until = path, place, float(error), until
        self.samples, self.since, self.cloud, self.deep, self.fetch = int(samples), since, float(cloud), float(deep), bool(fetch)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        folder = where(self.path, cache)
        name = self.place or folder.name
        if not (folder / f"{name}.json").is_file() and self.fetch:
            from ..fetch.get_reef import main
            folder.mkdir(parents=True, exist_ok=True)
            fetched(self.name, main, [name, grid.latitude, grid.longitude, "--across", grid.across,
                                      "--samples", self.samples, "--since", self.since, "--cloud", self.cloud,
                                      "--deep", self.deep, "--until", self.until, "--into", folder])
        said = json.loads((folder / f"{name}.json").read_text())
        field = said["heightfield"]
        height = np.fromfile(folder / field["file"], dtype="<f4").reshape(field["rows"], field["columns"])
        centre = said["centre"]
        same = (abs(centre["latitude"] - grid.latitude) < 1e-9 and abs(centre["longitude"] - grid.longitude) < 1e-9
                and abs(float(said["acrossMetres"]) - grid.across) < 1e-6 and height.shape == (grid.cells, grid.cells))
        if not same:
            height = _resampled(height, Grid(centre["latitude"], centre["longitude"], float(said["acrossMetres"]),
                                             height.shape[0]), grid)
        # get-reef writes the island at +0.6 m and every depth it read at or
        # below the surface, so land is what stands above it.
        land = np.where(np.isfinite(height), (height > 0.0).astype("float32"), np.nan)
        citation = (f"{said.get('method', 'Stumpf log-ratio')}, {said.get('source', 'Sentinel-2')} "
                    f"({said.get('observedAt', 'date not recorded')}); the depth scaled to the reef's own "
                    "geomorphology, not to anything measured")
        return [Layer.of(grid, "depth", height, self.error, Provenance(self.name, "derived", citation,
                                                                       "Copernicus open data", note_of(said))),
                Layer.of(grid, "land", land, 0.0,
                         Provenance(self.name, "derived", f"near infrared above 0.03 in {said.get('source')}",
                                    "Copernicus open data"))]


def _resampled(height: np.ndarray, was: Grid, grid: Grid) -> np.ndarray:
    """A heightfield on one square, bilinearly onto another; NaN off its edge."""
    from scipy.ndimage import map_coordinates

    lon, lat = grid.lonlat()
    x, y = was.to_xy(lon, lat)
    n = was.cells - 1
    col, row = (x / was.across + 0.5) * n, (y / was.across + 0.5) * n
    out = map_coordinates(height, [row, col], order=1, mode="constant", cval=np.nan)
    return out.astype("float32")
