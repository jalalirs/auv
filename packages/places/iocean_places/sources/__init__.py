"""Sources: one adapter per kind of data a place can be made from.

A source is anything with a `name`, the quantities it `gives`, and
`layers(grid, cache)` returning layers on the place's grid. It fetches or reads
its own data; fusion never knows where a layer came from beyond its
provenance. Step 2 of r8 moves the platform's existing tools in as sources
(GEBCO and the DCDB mosaic, ICESat-2, Sentinel-2, the Allen Coral Atlas, the
USGS surveys, fish records); these are the first few, and the interface.
"""

from __future__ import annotations

import json
import pathlib
from typing import Protocol

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance


class Source(Protocol):
    name: str
    gives: tuple[str, ...]

    def layers(self, grid: Grid, cache: pathlib.Path | None = None) -> list[Layer]: ...


class Points:
    """Soundings: x y z points, or longitude latitude depth, from a file of
    rows. Each cell takes the nearest point within `reach` metres; its error is
    the sounding's own plus the slope it may have missed over the distance
    (`slope` metres per metre), so a cell far from any sounding says so."""

    name = "points"
    gives = ("depth",)

    def __init__(self, path: str, error: float = 0.2, reach: float = 30.0, slope: float = 0.1,
                 degrees: bool = False, depths_positive: bool = False, kind: str = "measured",
                 citation: str = "") -> None:
        self.path, self.error, self.reach, self.slope = path, float(error), float(reach), float(slope)
        self.degrees, self.depths_positive, self.kind, self.citation = degrees, depths_positive, kind, citation

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        from scipy.spatial import cKDTree

        rows = np.loadtxt(self.path, delimiter="," if str(self.path).endswith(".csv") else None, ndmin=2)
        a, b, z = rows[:, 0], rows[:, 1], rows[:, 2]
        x, y = grid.to_xy(a, b) if self.degrees else (a, b)
        z = -z if self.depths_positive else z
        gx, gy = grid.xy()
        distance, nearest = cKDTree(np.column_stack([x, y])).query(np.column_stack([gx.ravel(), gy.ravel()]))
        distance, nearest = distance.reshape(gx.shape), nearest.reshape(gx.shape)
        near = distance <= self.reach
        value = np.where(near, z[nearest], np.nan)
        error = self.error + self.slope * distance
        return [Layer.of(grid, "depth", value, error,
                         Provenance(self.name, self.kind, self.citation or f"soundings in {pathlib.Path(self.path).name}"))]


class Place:
    """A place this platform already built: its heightfield as a depth layer,
    resampled onto the grid. How a rebuilt place is compared with the one the
    tools made, and how an old place becomes one source among several."""

    name = "place"
    gives = ("depth",)

    def __init__(self, path: str, error: float | None = None, kind: str | None = None) -> None:
        self.path, self.error, self.kind = pathlib.Path(path).expanduser(), error, kind

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        site = json.loads((self.path / "site.json").read_text())
        field = site["mesh"]["heightfield"]
        height = np.fromfile(self.path / field["file"], dtype="<f4").reshape(field["rows"], field["columns"])
        if height.shape != (grid.cells, grid.cells):
            from scipy.ndimage import zoom
            height = zoom(height, (grid.cells / height.shape[0], grid.cells / height.shape[1]), order=1)
        fitted = (site.get("from") or {}).get("fittedAgainst") or {}
        surveyed = bool((site.get("from") or {}).get("surveyed"))
        error = self.error if self.error is not None else float(fitted.get("rmsHeldOutM") or (0.5 if surveyed else 2.0))
        kind = self.kind or ("measured" if surveyed else "derived")
        return [Layer.of(grid, "depth", height, error,
                         Provenance(self.name, kind, f"the place {site.get('name', self.path.name)} as built"))]


class Flat:
    """A flat seabed at one depth: what a place is when nothing better is
    known, said to be assumed."""

    name = "flat"
    gives = ("depth",)

    def __init__(self, depth: float, error: float = 10.0) -> None:
        self.depth, self.error = float(depth), float(error)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        return [Layer.of(grid, "depth", np.full((grid.cells, grid.cells), -abs(self.depth)), self.error,
                         Provenance(self.name, "assumed", f"a flat seabed at {abs(self.depth)} m"))]


def _geotiff(**kw):
    from .geotiff import GeoTiff
    return GeoTiff(**kw)


# The recipe names a source by `use`; the rest of its entry are the source's arguments.
SOURCES = {"geotiff": _geotiff, "points": Points, "place": Place, "flat": Flat}


def source_from(entry: dict) -> Source:
    entry = dict(entry)
    use = entry.pop("use")
    if use not in SOURCES:
        raise ValueError(f"no source called {use!r}; there are {', '.join(sorted(SOURCES))}")
    return SOURCES[use](**entry)
