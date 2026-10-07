"""The training set for the depth model: chips of seabed with what Sentinel-2
saw over them and what was measured there.

A chip is 128 by 128 cells at 10 m, about 1.3 km square: enough for a network
to see a reef flat, its crest and the slope off it together. Each is saved as
one .npz: `x`, the Sentinel-2 band medians (the dataset config's bands, reflectance);
`y`, the measured height in each cell (NaN where nothing was measured);
`kind`, whether the label is dense (a lidar survey) or sparse (ICESat-2
photons along tracks). `index.jsonl` beside them says where each chip is,
which region it belongs to (models are tested on regions they never saw),
how much of it is labelled, and which scenes made its input.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np

from iocean_places.grid import Grid, metres_per_degree
from iocean_places.sources.raster import onto

CELLS = 128
CELL_M = 10.0
ACROSS = CELL_M * (CELLS - 1)
# A chip is kept when this much of it is water the label measured, between
# these heights: shallower is the surf and the shore, deeper is past where
# Sentinel-2 sees the bottom in the clearest water.
LABELLED_AT_LEAST = 0.25
SHALLOWEST, DEEPEST = -0.5, -30.0


def lattice(tiles: list[tuple[pathlib.Path, tuple]], step_m: float = ACROSS) -> list[tuple[float, float]]:
    """Chip centres every `step_m` over the tiles' bounds, kept where a tile is."""
    if not tiles:
        return []
    west = min(b[0] for _, b in tiles); south = min(b[1] for _, b in tiles)
    east = max(b[2] for _, b in tiles); north = max(b[3] for _, b in tiles)
    mid = (south + north) / 2
    e, n = metres_per_degree(mid)
    out = []
    lat = south + step_m / 2 / n
    while lat < north:
        e, n = metres_per_degree(lat)
        lon = west + step_m / 2 / e
        while lon < east:
            if any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3] for _, b in tiles):
                out.append((round(lat, 6), round(lon, 6)))
            lon += step_m / e
        lat += step_m / n
    return out


def lidar_label(grid: Grid, tiles: list[tuple[pathlib.Path, tuple]]) -> np.ndarray:
    """The lidar heights averaged into each cell, from every tile under the chip."""
    west, south, east, north = grid.bounds()
    out = np.full((grid.cells, grid.cells), np.nan)
    for path, b in tiles:
        if b[2] < west or b[0] > east or b[3] < south or b[1] > north:
            continue
        value, _ = onto(grid, path, average=True)
        out = np.where(np.isfinite(out), out, value)
    return out


def labelled_share(y: np.ndarray, shallowest: float = SHALLOWEST, deepest: float = DEEPEST) -> float:
    return float(((y < shallowest) & (y > deepest)).mean())


def photons_label(grid: Grid, lon: np.ndarray, lat: np.ndarray, height: np.ndarray) -> np.ndarray:
    """ICESat-2 photons into the cells they fell in, the median of each cell's."""
    x, y = grid.to_xy(lon, lat)
    inside = grid.inside(x, y)
    rows, cols = grid.nearest(x[inside], y[inside])
    out = np.full((grid.cells, grid.cells), np.nan)
    flat = rows * grid.cells + cols
    order = np.argsort(flat)
    flat, h = flat[order], height[inside][order]
    starts = np.flatnonzero(np.r_[True, np.diff(flat) != 0])
    for a, b in zip(starts, np.r_[starts[1:], len(flat)]):
        out.flat[flat[a]] = np.median(h[a:b])
    return out


def save(into: pathlib.Path, chip_id: str, x: np.ndarray, y: np.ndarray, kind: str, record: dict,
         shallowest: float = SHALLOWEST, deepest: float = DEEPEST) -> dict:
    into.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(into / f"{chip_id}.npz", x=x.astype("float32"), y=y.astype("float32"), kind=kind)
    record = {"chip": chip_id, "file": str((into / f"{chip_id}.npz").name), "labelKind": kind,
              "labelledShare": round(labelled_share(y, shallowest, deepest), 3), "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              **record}
    with open(into.parent / "index.jsonl", "a") as index:
        index.write(json.dumps(record) + "\n")
    return record


def chip_grid(latitude: float, longitude: float, cells: int = CELLS, cell_m: float = CELL_M) -> Grid:
    return Grid(latitude, longitude, cell_m * (cells - 1), cells)
