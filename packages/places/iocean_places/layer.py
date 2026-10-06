"""One shape for everything a place is made of.

A layer is a grid on the place's square with, in every cell, a value, how wrong
that value may be, and which source it came from. Depth, coral cover, habitat
class, colour: all layers. Two sources for the same square metre are then two
layers of the same quantity, and fusion can choose between them cell by cell.

A cell with no value is NaN. A source that covers only part of the square says
so by leaving the rest NaN, rather than by guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .grid import Grid

KINDS = ("measured", "derived", "chosen", "assumed")


@dataclass(frozen=True)
class Provenance:
    """Where a layer's numbers came from: which source, what kind of number
    (measured, derived, chosen or assumed, as everywhere on this platform),
    and the citation a person would follow."""

    source: str
    kind: str
    citation: str
    licence: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"a number is {', '.join(KINDS)}; not {self.kind!r}")

    def said(self) -> dict:
        return {"source": self.source, "kind": self.kind, "citation": self.citation,
                **({"licence": self.licence} if self.licence else {})}


@dataclass
class Layer:
    """`quantity` is what the values are ("depth" is height in metres, z up,
    0 at the surface, as the platform's heightfields are). `value` and `error`
    are (cells, cells). `source` is, per cell, an index into `provenance`;
    255 where there is no value."""

    grid: Grid
    quantity: str
    value: np.ndarray
    error: np.ndarray
    source: np.ndarray
    provenance: list[Provenance] = field(default_factory=list)

    NONE = 255

    @classmethod
    def of(cls, grid: Grid, quantity: str, value, error, provenance: Provenance) -> "Layer":
        """A layer from one source: error a number or a grid like the values."""
        value = np.asarray(value, dtype="float32")
        if value.shape != (grid.cells, grid.cells):
            raise ValueError(f"{quantity} is {value.shape}, the grid is {grid.cells} square")
        error = np.broadcast_to(np.asarray(error, dtype="float32"), value.shape).copy()
        source = np.where(np.isfinite(value), 0, cls.NONE).astype("u1")
        return cls(grid, quantity, value, error, source, [provenance])

    def covers(self) -> np.ndarray:
        """Which cells have a value."""
        return np.isfinite(self.value)

    def share(self) -> float:
        """How much of the square this layer covers."""
        return float(self.covers().mean())

    def said(self) -> dict:
        """What a place's record says about this layer: how much of it each
        source gave, and the error it carries, summarised."""
        out = []
        for k, p in enumerate(self.provenance):
            mine = self.source == k
            if not mine.any():
                continue
            out.append({**p.said(), "share": round(float(mine.mean()), 4),
                        "errorM": {"median": round(float(np.median(self.error[mine])), 3),
                                   "worst": round(float(np.max(self.error[mine])), 3)}})
        return {"quantity": self.quantity, "covered": round(self.share(), 4), "sources": out}
