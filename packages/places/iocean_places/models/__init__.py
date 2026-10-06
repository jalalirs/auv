"""Models: what turns some layers into another.

A model takes named layers and soundings (`take(name)`) and gives layers of its
own, each with an error it checked on data it was not fitted to, and a record
of how it was fitted. Today's are the two depth fits the tools made Shushah and
Al Fahal with; a learned depth model and coral cover from imagery come in
behind the same `run(grid, take)`.
"""

from __future__ import annotations

from typing import Callable, Protocol

from ..grid import Grid
from ..layer import Layer


class Model(Protocol):
    name: str
    gives: tuple[str, ...]
    inputs: dict[str, str | None]

    def run(self, grid: Grid, take: Callable) -> tuple[list[Layer], dict]: ...


def _curve(**kw):
    from .curve_depth import CurveDepth
    return CurveDepth(**kw)


def _colour(**kw):
    from .colour_depth import ColourDepth
    return ColourDepth(**kw)


def _datum(**kw):
    from .datum_fit import DatumFit
    return DatumFit(**kw)


MODELS = {"curve-depth": _curve, "colour-depth": _colour, "datum-fit": _datum}


def model_from(entry: dict) -> Model:
    entry = dict(entry)
    use = entry.pop("use")
    entry.pop("as", None)
    if use not in MODELS:
        raise ValueError(f"no model called {use!r}; there are {', '.join(sorted(MODELS))}")
    return MODELS[use](**entry)
