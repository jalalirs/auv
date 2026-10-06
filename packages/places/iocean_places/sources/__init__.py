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
from ..layer import Layer, Provenance, Soundings


# What a source's own record says about where its ground came from, carried
# into the place's record under the same keys (tools/built.py CARRIED, less the
# ones a build sets itself). A note without one of these deletes it from the
# place on the next rebuild: Al Fahal lost its scene and method that way.
NOTE_KEYS = ("source", "method", "observedAt", "opticalLimitM", "bottomVisibleFraction",
             "beyondOpticalDepthFraction", "medianDetailM", "toCalibrate", "constructedPastTheSensor")


def note_of(said: dict) -> dict:
    return {k: said[k] for k in NOTE_KEYS if k in said}


class Source(Protocol):
    """`layers` are on the grid; a source of measurements at points also has
    `soundings`, which models are fitted and checked against."""

    name: str
    gives: tuple[str, ...]

    def layers(self, grid: Grid, cache: pathlib.Path | None = None) -> list[Layer]: ...


def where(path: str | None, cache: pathlib.Path | None) -> pathlib.Path:
    """The folder a source reads from: its own `path`, else the recipe's cache."""
    if path:
        return pathlib.Path(path).expanduser()
    if cache is None:
        raise ValueError("this source reads from a folder: give it a path, or build with --cache")
    return pathlib.Path(cache).expanduser()


def gridded(grid: Grid, soundings: Soundings, reach: float, slope: float) -> Layer:
    """Soundings on the grid: each cell takes the nearest within `reach`
    metres, and its error is the sounding's own plus the slope it may have
    missed over the distance (`slope` metres per metre), so a cell far from
    any sounding says so."""
    from scipy.spatial import cKDTree

    gx, gy = grid.xy()
    distance, nearest = cKDTree(np.column_stack([soundings.x, soundings.y])).query(
        np.column_stack([gx.ravel(), gy.ravel()]))
    distance, nearest = distance.reshape(gx.shape), nearest.reshape(gx.shape)
    near = distance <= reach
    value = np.where(near, soundings.value[nearest], np.nan)
    error = soundings.error[nearest] + slope * distance
    return Layer.of(grid, soundings.quantity, value, error, soundings.provenance)


class Points:
    """Soundings: x y z points, or longitude latitude depth, from a file of
    rows; gridded as `gridded` says."""

    name = "points"
    gives = ("depth",)

    def __init__(self, path: str, error: float = 0.2, reach: float = 30.0, slope: float = 0.1,
                 degrees: bool = False, depths_positive: bool = False, kind: str = "measured",
                 citation: str = "") -> None:
        self.path, self.error, self.reach, self.slope = path, float(error), float(reach), float(slope)
        self.degrees, self.depths_positive, self.kind, self.citation = degrees, depths_positive, kind, citation

    def soundings(self, grid: Grid, cache=None) -> list[Soundings]:
        rows = np.loadtxt(self.path, delimiter="," if str(self.path).endswith(".csv") else None, ndmin=2)
        a, b, z = rows[:, 0], rows[:, 1], rows[:, 2]
        x, y = grid.to_xy(a, b) if self.degrees else (a, b)
        z = -z if self.depths_positive else z
        return [Soundings("depth", np.asarray(x, float), np.asarray(y, float), z, np.full(len(z), self.error),
                          Provenance(self.name, self.kind,
                                     self.citation or f"soundings in {pathlib.Path(self.path).name}"))]

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        return [gridded(grid, one, self.reach, self.slope) for one in self.soundings(grid, cache)]


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


def _lazy(module: str, name: str):
    def make(**kw):
        import importlib
        return getattr(importlib.import_module(f"{__name__}.{module}"), name)(**kw)
    return make


# The recipe names a source by `use`; the rest of its entry are the source's
# arguments, and `as` the name its layers go by (default: `use`).
SOURCES = {"geotiff": _geotiff, "points": Points, "place": Place, "flat": Flat,
           "sentinel2-median": _lazy("sentinel2", "Sentinel2Median"),
           "sentinel2-stumpf": _lazy("sentinel2", "Stumpf"),
           "icesat2": _lazy("icesat2", "IceSat2"),
           "allen-coral-atlas": _lazy("coral_atlas", "CoralAtlas"),
           "gebco": _lazy("gebco", "Gebco"),
           "bathymetry": _lazy("surveys", "Bathymetry"),
           "survey-dem": _lazy("surveys", "SurveyDem")}


def source_from(entry: dict) -> Source:
    entry = dict(entry)
    use = entry.pop("use")
    entry.pop("as", None)
    if use not in SOURCES:
        raise ValueError(f"no source called {use!r}; there are {', '.join(sorted(SOURCES))}")
    return SOURCES[use](**entry)
