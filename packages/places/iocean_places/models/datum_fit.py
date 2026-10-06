"""A survey's DEM onto a reference's datum, cleaned for fusion.

Moved from tools/ground. A survey's DEM comes in its own vertical datum (the
SQUID-5 DEM at Looe Key is NAVD88, the mosaic around it is not quite), so it is
shifted by the median of the difference where the two overlap, which is a
measurement of the offset and not an assumption about it. Then its small holes
are filled from their neighbours (up to `fillPasses` passes, where at least
three of the eight around a hole have a value), and specks smaller than
`smallestM2` are dropped: a few cells of survey standing alone are noise, not
a survey.
"""

from __future__ import annotations

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance


class DatumFit:
    name = "datum-fit"
    gives = ("depth",)

    def __init__(self, survey: str, reference: str, fillPasses: int = 6,  # noqa: N803 - the recipe's keys
                 smallestM2: float = 2000.0) -> None:
        self.inputs = {"survey": survey, "reference": reference}
        self.fill_passes, self.smallest_m2 = int(fillPasses), float(smallestM2)

    def run(self, grid: Grid, take) -> tuple[list[Layer], dict]:
        from scipy import ndimage

        survey, reference = take(self.inputs["survey"]), take(self.inputs["reference"])
        D = survey.value.astype(float)
        h = reference.value.astype(float)
        valid = np.isfinite(D) & np.isfinite(h)
        offset = float(np.nanmedian((D - h)[valid]))
        D -= offset
        filled = D.copy()
        passes = 0
        for _ in range(self.fill_passes):
            nan = ~np.isfinite(filled)
            if not nan.any():
                break
            total = ndimage.uniform_filter(np.nan_to_num(filled, nan=0.0), 3, mode="constant") * 9
            count = ndimage.uniform_filter(np.isfinite(filled).astype(float), 3, mode="constant") * 9
            filled = np.where(nan & (count >= 3), total / np.maximum(count, 1), filled)
            passes += 1
        have = np.isfinite(filled)
        labels, k = ndimage.label(have)
        sizes = ndimage.sum(have, labels, range(1, k + 1))
        smallest = self.smallest_m2 / grid.cell ** 2
        kept = have & np.isin(labels, 1 + np.flatnonzero(sizes > smallest))
        value = np.where(kept, filled, np.nan).astype("float32")
        error = np.where(kept, survey.error, np.nan).astype("float32")
        was = survey.provenance[0]
        cited = Provenance(was.source, was.kind,
                           f"{was.citation}; shifted {-offset:+.3f} m onto {reference.provenance[0].source}'s datum "
                           "(the median difference where they overlap), small holes filled, specks dropped",
                           was.licence, was.note)
        record = {"survey": was.source, "onto": reference.provenance[0].source,
                  "datumOffsetM": round(offset, 3), "overlapCells": int(valid.sum()),
                  "filledCells": int((have & ~np.isfinite(D)).sum()), "droppedCells": int((have & ~kept).sum()),
                  "coveredShare": round(float(kept.mean()), 4)}
        return [Layer(grid, "depth", value, error, np.where(kept, 0, Layer.NONE).astype("u1"), [cited])], record
