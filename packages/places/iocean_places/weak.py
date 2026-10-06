"""Where a place is weak: which of its cells were measured, which derived,
chosen or assumed, and how wrong each may be.

A place's record has always said where its ground came from as a whole. This
says it cell by cell, because a seabed that is 1 m good on average can be
6 m out exactly where a vehicle is sent: the colour fit at Shushah is under a
metre at 10 to 15 m and over four between 5 and 10.
"""

from __future__ import annotations

import numpy as np

from .layer import KINDS, Layer

# How wrong a cell may be, in bands, and the colour each is drawn in.
BANDS = ((0.0, 0.5, (46, 125, 50)), (0.5, 1.0, (124, 179, 66)), (1.0, 2.0, (253, 216, 53)),
         (2.0, 5.0, (251, 140, 0)), (5.0, np.inf, (198, 40, 40)))
NO_VALUE = (120, 120, 120)
LAND = (215, 200, 160)
BLOCK_M = 100.0


def _label(low: float, high: float) -> str:
    return f"under {high:g} m" if low == 0 else (f"{low:g} m and worse" if not np.isfinite(high) else f"{low:g} to {high:g} m")


def weak_of(depth: Layer, begin_at: list | None = None, worst: int = 5) -> dict:
    """The summary a place's record carries under from.depth.weak."""
    grid, error = depth.grid, depth.error
    # Land is not seabed: it is said as land, and its error is not a seabed's.
    land = depth.covers() & (depth.value > 0.0)
    has = depth.covers() & np.isfinite(error) & ~land
    kinds = np.full(error.shape, "", dtype=object)
    for k, p in enumerate(depth.provenance):
        kinds[depth.source == k] = p.kind
    out = {
        "byKind": {kind: round(float((kinds == kind).mean()), 4) for kind in KINDS if (kinds == kind).any()},
        "errorM": {"median": round(float(np.median(error[has])), 2),
                   "p90": round(float(np.percentile(error[has], 90)), 2),
                   "worst": round(float(error[has].max()), 2)},
        "byError": {_label(lo, hi): round(float(((error >= lo) & (error < hi) & has).sum() / max(1, has.sum())), 4)
                    for lo, hi, _ in BANDS},
        "byErrorIsOf": "the seabed: the share of underwater cells in each band",
        "landShare": round(float(land.mean()), 4),
        "errorIs": ("per cell, from the source that made it: a measurement's own uncertainty, or a model's "
                    "held-out error at the cell's depth"),
    }
    # The weakest blocks, so somebody planning a dive knows where not to trust it.
    n = max(1, int(round(BLOCK_M / grid.cell)))
    rows, cols = error.shape[0] // n, error.shape[1] // n
    if rows and cols:
        blocks = np.where(has, error, np.nan)[:rows * n, :cols * n].reshape(rows, n, cols, n)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)   # a block all land has no seabed
                median = np.nanmedian(blocks, axis=(1, 3))
        order = np.argsort(np.nan_to_num(median, nan=-1.0), axis=None)[::-1][:worst]
        weakest = []
        for flat in order:
            r, c = np.unravel_index(flat, median.shape)
            src = depth.source[r * n:(r + 1) * n, c * n:(c + 1) * n]
            common = np.bincount(src.ravel()[src.ravel() != Layer.NONE], minlength=len(depth.provenance)).argmax() \
                if (src != Layer.NONE).any() else None
            x = ((c + 0.5) * n / (grid.cells - 1) - 0.5) * grid.across
            y = ((r + 0.5) * n / (grid.cells - 1) - 0.5) * grid.across
            weakest.append({"at": [round(float(x), 1), round(float(y), 1)], "acrossM": round(n * grid.cell, 1),
                            "medianErrorM": round(float(median[r, c]), 2),
                            "from": depth.provenance[common].source if common is not None else None})
        out["weakest"] = weakest
    if begin_at:
        r, c = grid.nearest(begin_at[0], begin_at[1])
        out["atBeginM"] = round(float(error[r, c]), 2) if has[r, c] else None
    return out


def picture(depth: Layer) -> np.ndarray:
    """An RGB picture of the place's error, north up: green where it is good
    to half a metre, through yellow and orange, to red where it may be five
    metres out or worse; grey where nothing gave a value."""
    error = depth.error
    rgb = np.empty(error.shape + (3,), dtype="uint8")
    rgb[:] = NO_VALUE
    land = depth.covers() & (depth.value > 0.0)
    has = depth.covers() & np.isfinite(error) & ~land
    for lo, hi, colour in BANDS:
        rgb[has & (error >= lo) & (error < hi)] = colour
    rgb[land] = LAND
    return rgb[::-1]


def legend() -> list[dict]:
    return ([{"errorM": _label(lo, hi), "rgb": list(c)} for lo, hi, c in BANDS]
            + [{"errorM": "land", "rgb": list(LAND)}, {"errorM": "no value", "rgb": list(NO_VALUE)}])
