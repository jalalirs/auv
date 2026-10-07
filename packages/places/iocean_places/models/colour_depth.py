"""Depth from the colour and the reef map, fitted to measured depths.

Moved from tools/fit-colour-depths, which now uses it from here. One curve of
the claim is right when the claim is a good shape at the wrong scale, and wrong
when two different bottoms give the same claim. At Shushah they do: Stumpf's
log-ratio reads the bright 14 m sand terrace like the bright 1 m reef flat. What
tells them apart is the colour itself (the blue, green and red that came back,
not only their ratio) and the Allen Coral Atlas's map of which ground is reef
flat, crest and slope. So this fits the measured depth on all of them at once,
by least squares, the way satellite-derived bathymetry has been trained on
ICESat-2 since it flew (Ma et al. 2020; Babbel et al. 2021), and checks it by
holding out 200 m blocks of the site in turn.

It speaks only where the colour is the bottom's: not on land, not deeper than
the measured depths reach (with a margin), and not above the surface. Elsewhere
it says nothing, and fusion takes the next source.
"""

from __future__ import annotations

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance
from .curve_depth import BLOCK_M, blocks_of, error_of_cells, held_out_by_depth

BEYOND_M = 3.0
# The shallowest the colour may put a cell it speaks for: awash, never dry.
AWASH_M = -0.1


def features(claimed, colour, cls, n_classes, soften_cells: float = 0.0):
    """What the fit is on, for any set of cells: claimed depth, the log-ratio,
    the log of each band, and the class as one column each.

    A class's column is softened over `soften_cells` (a Gaussian's sigma):
    each class buys a constant depth offset (6.75 m for the inner reef flat at
    Shushah), and a hard 0 or 1 puts that offset down as a cliff along every
    edge of the atlas's polygons. Softened, it ramps across the edge, and the
    fit learns the offset all the same, inside the polygons where the photons
    are."""
    blue, green, red = (np.maximum(colour[..., k], 1e-4) for k in (2, 1, 0))
    columns = [np.ones_like(claimed), claimed, np.log(1000 * blue) / np.log(1000 * green),
               np.log(blue), np.log(green), np.log(red)]
    for k in range(1, n_classes + 1):
        one = (cls == k).astype(float)
        if soften_cells > 0:
            from scipy.ndimage import gaussian_filter
            one = gaussian_filter(one, soften_cells, mode="nearest")
        columns.append(one)
    return np.stack(columns, axis=-1)


def by_depth(measured, predicted):
    bands = []
    for low, high in ((0, 2), (2, 5), (5, 10), (10, 15), (15, 25), (25, None)):
        depth = -measured
        inside = (depth >= low) & ((depth < high) if high is not None else True)
        if inside.sum() < 20:
            continue
        e = predicted[inside] - measured[inside]
        bands.append({"fromM": low, "toM": high, "points": int(inside.sum()),
                      "medianM": round(float(np.median(e)), 2), "rmsM": round(float(np.sqrt(np.mean(e ** 2))), 2)})
    return bands


def held_out(F, measured, blocks):
    """Each block predicted by a fit to the others."""
    out = np.full(len(measured), np.nan)
    for block in np.unique(blocks):
        test = blocks == block
        coefficients, *_ = np.linalg.lstsq(F[~test], measured[~test], rcond=None)
        out[test] = F[test] @ coefficients
    return out


def rms(e) -> float:
    return float(np.sqrt(np.mean(e ** 2)))


class ColourDepth:
    """`depth`: the claimed depth; `red`, `green`, `blue`: the colour layers;
    `classes`: the reef map's geomorphic classes; `truth`: measured soundings;
    `land` (optional): 1 on land, where the reef map does not call it reef."""

    name = "colour-depth"
    gives = ("depth",)

    def __init__(self, depth: str, red: str, green: str, blue: str, classes: str, truth: str,
                 land: str | None = None, softenClassesM: float = 20.0) -> None:  # noqa: N803 - the recipe's key
        self.inputs = {"depth": depth, "red": red, "green": green, "blue": blue, "classes": classes,
                       "truth": truth, "land": land}
        self.soften_m = float(softenClassesM)

    def run(self, grid: Grid, take) -> tuple[list[Layer], dict]:
        claimed = take(self.inputs["depth"]).value.astype(float)
        colour = np.stack([take(self.inputs[b]).value for b in ("red", "green", "blue")], axis=-1).astype(float)
        reef_map = take(self.inputs["classes"])
        cls, names = reef_map.codes(), reef_map.classes or ()
        # Fitted on the classes as the atlas draws them, drawn with them softened.
        # Fitted softened, a class with no photons of its own is still a few
        # per cent present beside one that has, and the least-squares buys it
        # a coefficient of hundreds of metres out of that (Looe Key's held-out
        # error went from 0.87 m to 407 m). The offsets come from the hard
        # classes; only where they are laid down is softened.
        every = features(claimed, colour, cls, len(names))
        drawn = features(claimed, colour, cls, len(names), self.soften_m / grid.cell)

        truth = take(self.inputs["truth"])
        x, y, measured = truth.x, truth.y, truth.value
        i, j = grid.nearest(x, y)
        usable = (grid.inside(x, y) & (measured < -0.2)
                  & np.all(colour[i, j] > 0, axis=-1) & np.isfinite(claimed[i, j]))
        x, y, measured, i, j = x[usable], y[usable], measured[usable], i[usable], j[usable]
        F = every[i, j]
        blocks = blocks_of(x, y, grid.across)

        curve = held_out(F[:, :2], measured, blocks)
        colour_fit = held_out(F, measured, blocks)
        error = rms(colour_fit - measured)
        coefficients, *_ = np.linalg.lstsq(F, measured, rcond=None)
        heights = drawn @ coefficients
        deepest, shallowest = float(measured.min()), float(measured.max())

        land = np.zeros(claimed.shape, bool)
        if self.inputs["land"]:
            land = (take(self.inputs["land"]).value == 1.0) & (cls == 0)
        seen = np.all(colour > 0, axis=-1) & (heights > deepest - BEYOND_M) & (heights < 0.5) & ~land
        value = np.where(seen, np.minimum(heights, AWASH_M), np.nan).astype("float32")

        record = {
            "source": truth.provenance.citation, "points": int(len(measured)),
            "on": ["the claimed depth", "ln(1000 B)/ln(1000 G)", "ln B", "ln G", "ln R"]
                  + [f"{reef_map.provenance[0].citation.split(' map')[0]} class: {n}" for n in names],
            "coefficients": [round(float(c), 5) for c in coefficients],
            "heldOut": f"blocks of {BLOCK_M:.0f} m, each predicted from a fit to the others",
            "rmsHeldOutM": round(error, 2), "rmsHeldOutOneCurveM": round(rms(curve - measured), 2),
            "residualByDepth": by_depth(measured, colour_fit),
            "heldOutByDepth": held_out_by_depth(measured, colour_fit),
            "calibratedBetweenM": [round(-shallowest, 1), round(-deepest, 1)],
            "fromColourShare": round(float(seen.mean()), 3),
            "elsewhere": "the next source fusion believes, where the colour is not the bottom's",
            "note": ("derived from the colour and the reef map, fitted to measured depths. "
                     "Not a survey: a derived seabed with a known, held-out error."),
        }
        claim = take(self.inputs["depth"]).provenance[0]
        note = {k: v for k, v in claim.note.items() if k != "toCalibrate"}
        if "toCalibrate" in claim.note:
            record["wasOwed"] = claim.note["toCalibrate"]
        cited = Provenance(self.name, "derived",
                           f"{', '.join(sorted({take(self.inputs[b]).provenance[0].source for b in ('red', 'green', 'blue')}))}"
                           f" colour and the {reef_map.provenance[0].source} reef map, fitted to "
                           f"{truth.provenance.source}, held-out rms {error:.2f} m", note=note)
        per_cell = error_of_cells(value, record["heldOutByDepth"], deepest, error)
        layer = Layer.of(grid, "depth", value, per_cell, cited)
        layer.rank = error
        return [layer], record
