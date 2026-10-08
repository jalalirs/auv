"""One curve of the claim: a satellite-derived depth rescaled to measured ones.

Moved from tools/fit-depths, which now uses it from here. Satellite-derived
bathymetry reads shape off how much light comes back from the bottom; the
shape is usually good and the scale is a fit against an assumed water column,
so when the assumption is wrong the whole seabed is wrong together. This fits
the claimed depth to measured ones, drops what the fit itself calls an outlier,
tries a few shapes and keeps the simplest whose worst depth band is not
meaningfully beaten, and applies it to the whole square.

It does not make the seabed measured. It makes it a derived seabed with a known
error: the error of a 200 m block of the site predicted from a fit to the
others, so a sounding is never scored against a line through its own track.
"""

from __future__ import annotations

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance

# How far past the measured range the fit may be trusted before it is
# extrapolation. ICESat-2 sees to about 1.5 Secchi depths and no further.
BEYOND_M = 3.0
BLOCK_M = 200.0
BANDS = ((0.0, 5.0), (5.0, 10.0), (10.0, 15.0), (15.0, 25.0), (25.0, None))
# How much better a more complicated shape has to be before it is worth it.
# Over Al Fahal the curve bought 1.37 m in a band holding 56 points and cost
# 1.34 m in the band holding 22,430: a worse seabed everywhere anybody flies.
WORTH_IT_M = 2.0
WORTH_IT_SHARE = 0.25
# Where a fit stops holding. A band further out than this is not calibrated,
# whatever the overall rms says.
HOLDS_WITHIN_M = 3.0
# Bright reef the near infrared took for island, and the reef map says is reef:
# awash rather than dry, at a depth chosen, not measured.
AWASH_M = -0.3


def sample(field, across: float, x, y):
    """What a heightfield says at a scatter of points."""
    rows, columns = field.shape
    u = np.clip((x / across + 0.5) * (columns - 1), 0, columns - 1.001)
    v = np.clip((y / across + 0.5) * (rows - 1), 0, rows - 1.001)
    i, j = u.astype(int), v.astype(int)
    fu, fv = u - i, v - j
    return ((field[j, i] * (1 - fu) + field[j, i + 1] * fu) * (1 - fv)
            + (field[j + 1, i] * (1 - fu) + field[j + 1, i + 1] * fu) * fv)


def spread_of(residual):
    middle = float(np.median(residual))
    return middle, float(np.median(np.abs(residual - middle)) * 1.4826)


def what_is_left_by_depth(measured, fitted):
    """The residual by depth band, because one rms hides its own shape.

    Al Fahal fitted to rms 2.00 m from 10.50 m, which reads as solved. It is
    not: 22,430 of its 26,726 measured depths are in the top five metres, so
    the line is theirs, and what is left runs +0.62 m there and -16.35 m
    between fifteen and twenty-five. `measured` and `fitted` are negative-down.
    """
    left = np.asarray(measured) - np.asarray(fitted)
    depth = -np.asarray(measured)
    out = []
    for near, far in BANDS:
        inside = (depth >= near) if far is None else ((depth >= near) & (depth < far))
        if not inside.any():
            continue
        out.append({"fromM": near, "toM": far, "points": int(inside.sum()),
                    "medianM": round(float(np.median(left[inside])), 2),
                    "rmsM": round(float(np.sqrt(np.mean(left[inside] ** 2))), 2)})
    return out


def worst_band(bands):
    """The band furthest out, by median. None when there are no bands."""
    return max(bands, key=lambda b: abs(b["medianM"]), default=None) or None


def band_weights(measured):
    """One weight per point, so each depth band counts for as much as another."""
    depth = -np.asarray(measured)
    w = np.ones(len(depth))
    for near, far in BANDS:
        inside = (depth >= near) if far is None else ((depth >= near) & (depth < far))
        if inside.any():
            w[inside] = 1.0 / float(inside.sum())
    return w


def candidate_fits(said, measured, weights):
    """The fits worth trying, each as (name, curve). A straight line is the
    right shape for a log-ratio in principle; in practice the claim saturates
    near its optical limit, which a second-order term can hold."""
    out = [("straight line", np.polyfit(said, measured, 1)),
           ("straight line, bands balanced", np.polyfit(said, measured, 1, w=np.sqrt(weights)))]
    if len(said) > 12:
        out.append(("curved, bands balanced", np.polyfit(said, measured, 2, w=np.sqrt(weights))))
    return [(name, np.poly1d(c)) for name, c in out]


def rises_with_depth(curve, said):
    """A fit that turns back on itself over the claimed range is not a rescaling."""
    grid = np.linspace(float(np.min(said)), float(np.max(said)), 256)
    step = np.diff(curve(grid))
    return bool(np.all(step >= 0) or np.all(step <= 0))


def how_bad_at_worst(measured, fitted):
    """The score a fit is chosen on: its furthest band, not its overall rms."""
    worst = worst_band(what_is_left_by_depth(measured, fitted))
    return abs(worst["medianM"]) if worst else 0.0


def simplest_good_enough(tried):
    """The simplest shape, unless a longer one is meaningfully better.
    `tried` is (name, curve, worst_band_metres, why_not), simplest first."""
    usable = [t for t in tried if t[2] is not None]
    if not usable:
        return None
    best = usable[0]
    for other in usable[1:]:
        gain = abs(best[2]) - abs(other[2])
        if gain >= WORTH_IT_M and gain >= WORTH_IT_SHARE * abs(best[2]):
            best = other
    return best


def holds_to(bands):
    """The depth this fit is good to, and the bands past it."""
    good = None
    for band in bands:
        if abs(band["medianM"]) <= HOLDS_WITHIN_M:
            good = band["toM"] if band["toM"] is not None else band["fromM"]
        else:
            break
    past = [b for b in bands if abs(b["medianM"]) > HOLDS_WITHIN_M]
    return good, past


def fit(said, measured):
    """Fit, drop what the fit calls an outlier (three robust sigma), and keep
    the simplest shape whose worst band is not meaningfully beaten. Returns
    (name, curve, kept, tried), or None when no shape holds."""
    slope, offset = np.polyfit(said, measured, 1)
    residual = measured - (slope * said + offset)
    middle, spread = spread_of(residual)
    keep = np.abs(residual - middle) < 3 * spread
    weights = band_weights(measured[keep])
    tried = []
    for name, curve in candidate_fits(said[keep], measured[keep], weights):
        if not rises_with_depth(curve, said[keep]):
            tried.append((name, curve, None, "turns back on itself"))
            continue
        tried.append((name, curve, how_bad_at_worst(measured, curve(said)), None))
    picked = simplest_good_enough(tried)
    if picked is None:
        return None
    return picked[0], picked[1], keep, tried


def blocks_of(x, y, across: float, block: float = BLOCK_M) -> np.ndarray:
    return (np.floor((x + across / 2) / block) * 1000 + np.floor((y + across / 2) / block)).astype(int)


def held_out(said, measured, blocks, kept, degree: int, balanced: bool) -> np.ndarray:
    """Each block predicted by the chosen shape fitted to the others' kept
    points, and scored on every point in it: what the fit dropped as an
    outlier is still somewhere a vehicle may fly. NaN where a block could not
    be predicted."""
    out = np.full(len(measured), np.nan)
    for block in np.unique(blocks):
        test = blocks == block
        train = ~test & kept
        if train.sum() <= degree + 1:
            continue
        w = np.sqrt(band_weights(measured[train])) if balanced else None
        out[test] = np.poly1d(np.polyfit(said[train], measured[train], degree, w=w))(said[test])
    return out


def held_out_rms(said, measured, blocks, kept, degree: int, balanced: bool) -> float:
    out = held_out(said, measured, blocks, kept, degree, balanced)
    ok = np.isfinite(out)
    return float(np.sqrt(np.mean((out[ok] - measured[ok]) ** 2)))


# Fewer held-out points than this in a depth band and its rms is not a number
# to give a cell; the band takes its neighbours' instead.
FEWEST_IN_A_BAND = 20


def held_out_by_depth(measured, predicted, edges=(0, 2, 5, 10, 15, 25, 40)) -> list[dict]:
    """The held-out error in depth bands, by the depth a fit *predicted*
    (which is the depth a cell has; the measured one is not known there)."""
    ok = np.isfinite(predicted)
    depth, e = -predicted[ok], predicted[ok] - measured[ok]
    out = []
    for low, high in zip(edges[:-1], edges[1:]):
        inside = (depth >= low) & (depth < high)
        if inside.sum() >= FEWEST_IN_A_BAND:
            out.append({"fromM": low, "toM": high, "points": int(inside.sum()),
                        "rmsM": round(float(np.sqrt(np.mean(e[inside] ** 2))), 3)})
    return out


# Past the deepest depth anybody measured, a fit is extrapolating, and how
# wrong it may be grows with how far: chosen, half a metre a metre.
EXTRAPOLATING_PER_M = 0.5


def error_of_cells(value: np.ndarray, bands: list[dict], deepest_measured: float, overall: float) -> np.ndarray:
    """Each cell's error: the held-out rms at its depth, interpolated between
    band middles so that fusion never sees a step at a band's edge, and
    growing past the deepest measured depth."""
    if not bands:
        return np.full(value.shape, overall, dtype="float32")
    middles = np.array([(b["fromM"] + b["toM"]) / 2 for b in bands])
    rms = np.array([b["rmsM"] for b in bands])
    depth = np.clip(-value.astype(float), 0.0, None)
    error = np.interp(depth, middles, rms)
    past = np.clip(depth - abs(deepest_measured), 0.0, None)
    return (error + EXTRAPOLATING_PER_M * past).astype("float32")


class CurveDepth:
    """`depth`: the claimed depth layer; `truth`: measured soundings; `land`
    (optional): a layer that is 1 on land, kept at its claimed height;
    `reef` (optional): a layer of classes, where land the reef map calls reef
    is awash instead. `keepWet`: a cell the claim has under water stays under
    water. A line fitted to depths of half a metre and more says nothing about
    the surface, and Al Fahal's (+2.96 m offset) put 32 hectares of its reef
    flat up to three metres above the sea; off only to rebuild a place as it
    was built."""

    name = "curve-depth"
    gives = ("depth",)

    def __init__(self, depth: str, truth: str, land: str | None = None, reef: str | None = None,
                 landHeight: str | None = None,
                 kind: str = "derived", keepWet: bool = True) -> None:
        self.inputs = {"depth": depth, "truth": truth, "land": land, "reef": reef, "landHeight": landHeight}
        self.kind, self.keep_wet = kind, bool(keepWet)

    def run(self, grid: Grid, take) -> tuple[list[Layer], dict]:
        claims = take(self.inputs["depth"]).value
        truth = take(self.inputs["truth"])
        across = grid.across
        x, y, measured = truth.x, truth.y, truth.value
        inside = grid.inside(x, y) & (measured < -0.5)
        x, y, measured = x[inside], y[inside], measured[inside]
        said = sample(claims, across, x, y)
        got = fit(said, measured)
        if got is None:
            raise ValueError(f"{self.name}: no shape holds over this range")
        chosen, curve, keep, tried = got
        fitted = curve(said)
        bands = what_is_left_by_depth(measured, fitted)
        good_to, past = holds_to(bands)
        blocks = blocks_of(x, y, across)
        predicted = held_out(said, measured, blocks, keep, curve.order, "balanced" in chosen)
        ok = np.isfinite(predicted)
        error = float(np.sqrt(np.mean((predicted[ok] - measured[ok]) ** 2)))
        bands_held_out = held_out_by_depth(measured, predicted)

        value = curve(claims).astype("float32")
        land = np.zeros(claims.shape, bool)
        if self.inputs["land"]:
            land = take(self.inputs["land"]).value == 1.0
        awash = np.zeros(claims.shape, bool)
        if self.inputs["reef"] is not None:
            awash = land & (take(self.inputs["reef"]).codes() > 0)
        # Land at its own height: the claim's, or a layer that knows land (the
        # learned depth model knows only water, so a recipe hands it the
        # satellite's land height).
        on_land = take(self.inputs["landHeight"]).value if self.inputs["landHeight"] else claims
        value = np.where(land & ~awash, on_land, value)
        value = np.where(awash, np.float32(AWASH_M), value).astype("float32")
        wet = ~land & (claims <= 0.0) & (value > AWASH_M)
        if self.keep_wet:
            value = np.where(wet, np.float32(AWASH_M), value).astype("float32")

        deepest, shallowest = float(measured.min()), float(measured.max())
        corrected = value[~land]
        beyond = float(((corrected < deepest - BEYOND_M) | (corrected > shallowest + BEYOND_M)).mean())
        record = {
            "source": truth.provenance.citation, "points": int(len(x)), "shape": chosen,
            "coefficients": [float(c) for c in curve.coefficients],
            "triedOnWorstBand": {name: (why or round(score, 2)) for name, _c, score, why in tried},
            "rmsAfterM": round(float(np.sqrt(np.mean((measured - fitted) ** 2))), 2),
            "rmsHeldOutM": round(error, 2), "heldOut": f"blocks of {BLOCK_M:.0f} m, each predicted from a fit to the others",
            "residualByDepth": bands, "heldOutByDepth": bands_held_out,
            "calibratedToM": good_to, "pastThatUncalibrated": bool(past),
            "calibratedBetweenM": [round(-shallowest, 1), round(-deepest, 1)], "extrapolatedShare": round(beyond, 3),
            "landKeptCells": int((land & ~awash).sum()), "awashCells": int(awash.sum()),
            ("keptWetCells" if self.keep_wet else "driedCells"): int(wet.sum()),
            "note": "derived from a satellite claim rescaled to measured depths. Not a survey: a derived seabed with a known, held-out error.",
        }
        claim = take(self.inputs["depth"]).provenance[0]
        # The claim's own record, carried; less what was owed, which this fit answers.
        note = {k: v for k, v in claim.note.items() if k != "toCalibrate"}
        if "toCalibrate" in claim.note:
            record["wasOwed"] = claim.note["toCalibrate"]
        cited = Provenance(self.name, self.kind,
                           f"{claim.source} rescaled by a {chosen} to "
                           f"{truth.provenance.source}, held-out rms {error:.2f} m", note=note)
        per_cell = error_of_cells(value, bands_held_out, deepest, error)
        layer = Layer.of(grid, "depth", value, per_cell, cited)
        layer.rank = error
        return [layer], record
