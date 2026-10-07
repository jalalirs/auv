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

    def __init__(self, survey: str, reference: str | None = None, fillPasses: int = 6,
                 smallestM2: float = 2000.0, offsetM: float | None = None, fewestOverlapCells: int = 200,
                 allowDerived: bool = False) -> None:
        self.inputs = {"survey": survey, "reference": reference}
        self.fill_passes, self.smallest_m2 = int(fillPasses), float(smallestM2)
        self.offset_m, self.fewest = (None if offsetM is None else float(offsetM)), int(fewestOverlapCells)
        self.allow_derived = bool(allowDerived)
        if reference is None and offsetM is None:
            raise ValueError("datum-fit needs a reference layer to measure the offset against, or an offsetM to apply")

    def run(self, grid: Grid, take) -> tuple[list[Layer], dict]:
        from scipy import ndimage

        survey = take(self.inputs["survey"])
        reference = take(self.inputs["reference"]) if self.inputs["reference"] else None
        D = survey.value.astype(float)
        if self.offset_m is not None:
            # Declared: the client knows its datum's offset (a chart datum to
            # mean sea level, say), and the record says it was chosen.
            valid, offset, onto = np.zeros(D.shape, bool), self.offset_m, "an offset the recipe declares"
        else:
            # A datum is measured against something measured. Fitted onto a
            # satellite fit, Looe Key's survey took on that fit's local bias
            # and moved 1.59 m: the fit was 0.87 m good on average and 1.5 m
            # out over that patch of reef.
            if reference.provenance[0].kind != "measured" and not self.allow_derived:
                raise ValueError(
                    f"{self.name}: {reference.provenance[0].source} is {reference.provenance[0].kind}, and a datum "
                    "fitted onto it takes on its local bias; fit onto something measured, declare offsetM, "
                    "or say allowDerived")
            h = reference.value.astype(float)
            valid = np.isfinite(D) & np.isfinite(h)
            if valid.sum() < self.fewest:
                # A median of nothing is NaN, and a NaN offset empties the survey
                # without a word: at Looe Key no ICESat-2 track crosses the SQUID-5
                # footprint, and the client's survey vanished from the place.
                raise ValueError(
                    f"{self.name}: {survey.provenance[0].source} and {reference.provenance[0].source} overlap in "
                    f"{int(valid.sum())} cells, too few to measure a datum; fit onto a layer that covers it "
                    "(a satellite fit calibrated to the laser) or declare offsetM")
            offset = float(np.nanmedian((D - h)[valid]))
            onto = f"{reference.provenance[0].source}'s datum (the median difference where they overlap)"
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
                           f"{was.citation}; shifted {-offset:+.3f} m onto {onto}, small holes filled, specks dropped",
                           was.licence, was.note)
        record = {"survey": was.source, "onto": reference.provenance[0].source if reference else "declared",
                  "offsetIs": "chosen" if self.offset_m is not None else "measured",
                  "datumOffsetM": round(offset, 3), "overlapCells": int(valid.sum()),
                  "filledCells": int((have & ~np.isfinite(D)).sum()), "droppedCells": int((have & ~kept).sum()),
                  "coveredShare": round(float(kept.mean()), 4)}
        return [Layer(grid, "depth", value, error, np.where(kept, 0, Layer.NONE).astype("u1"), [cited])], record
