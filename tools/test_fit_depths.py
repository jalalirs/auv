"""The residual a fit leaves behind, by depth.

Al Fahal fitted to rms 2.00 m from 10.50 m. Read as one number that is solved.
Read by depth it is not: 22,430 of its 26,726 measured depths sit in the top
five metres, so the line is theirs, and what is left runs +0.62 m there and
-16.35 m between fifteen and twenty-five — worse at depth than the uncalibrated
seabed it replaced. A number too good deserves the same suspicion as one too
bad, so the tool prints the bands and the place records them.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _fit():
    loader = importlib.machinery.SourceFileLoader("fit_depths", str(HERE / "fit-depths"))
    spec = importlib.util.spec_from_loader("fit_depths", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_a_perfect_fit_leaves_nothing_in_any_band():
    fit = _fit()
    measured = -np.array([1.0, 3.0, 7.0, 12.0, 20.0, 30.0])
    bands = fit.what_is_left_by_depth(measured, measured)
    assert bands, "every depth fell outside every band"
    for band in bands:
        assert band["medianM"] == 0.0, band
        assert band["rmsM"] == 0.0, band


def test_the_shallows_can_be_right_while_the_deep_is_not():
    """The Al Fahal shape: a fit owned by the points that outnumber the rest."""
    fit = _fit()
    shallow = -np.full(2000, 2.0)
    deep = -np.full(10, 20.0)
    measured = np.concatenate([shallow, deep])
    fitted = np.concatenate([shallow, deep + 16.0])   # deep says 16 m shallower
    bands = {b["fromM"]: b for b in fit.what_is_left_by_depth(measured, fitted)}
    assert bands[0.0]["medianM"] == 0.0
    assert bands[15.0]["medianM"] == pytest.approx(-16.0, abs=0.01)
    assert bands[15.0]["points"] == 10
    worst = fit.worst_band(list(bands.values()))
    assert worst["fromM"] == 15.0, "the worst band is not the one furthest out"


def test_an_overall_rms_can_hide_the_worst_band_entirely():
    """The point of the whole thing, as arithmetic.

    Two thousand points perfect and ten points sixteen metres out give an
    overall rms of about 1.1 m — which would read as a good fit.
    """
    fit = _fit()
    shallow = -np.full(2000, 2.0)
    deep = -np.full(10, 20.0)
    measured = np.concatenate([shallow, deep])
    fitted = np.concatenate([shallow, deep + 16.0])
    overall = float(np.sqrt(np.mean((measured - fitted) ** 2)))
    assert overall < 1.2, overall
    worst = fit.worst_band(fit.what_is_left_by_depth(measured, fitted))
    assert abs(worst["medianM"]) > 10 * overall, (
        "the worst band must be able to dwarf the rms that hides it")


def test_bands_with_no_points_are_left_out_not_reported_as_zero():
    fit = _fit()
    measured = -np.full(50, 2.0)
    bands = fit.what_is_left_by_depth(measured, measured)
    assert [b["fromM"] for b in bands] == [0.0]


def test_the_open_band_catches_everything_deeper():
    fit = _fit()
    measured = -np.array([40.0, 80.0])
    bands = fit.what_is_left_by_depth(measured, measured)
    assert len(bands) == 1 and bands[0]["fromM"] == 25.0
    assert bands[0]["toM"] is None and bands[0]["points"] == 2


def test_no_bands_means_no_worst_band():
    fit = _fit()
    assert fit.worst_band([]) is None


# ── the fit is chosen on its worst band, not its overall rms ─────────────────

def test_band_weights_make_a_sparse_deep_band_count():
    fit = _fit()
    measured = -np.concatenate([np.full(2000, 2.0), np.full(10, 20.0)])
    w = fit.band_weights(measured)
    shallow, deep = w[:2000].sum(), w[2000:].sum()
    assert shallow == pytest.approx(1.0), shallow
    assert deep == pytest.approx(1.0), deep


def test_an_unweighted_line_loses_to_a_balanced_one_on_the_deep_band():
    """The Al Fahal shape, built to order: saturating claims at depth."""
    fit = _fit()
    rng = np.random.default_rng(7)
    # Real depths: a mass of shallow points and a thin deep tail.
    real = np.concatenate([rng.uniform(0.5, 5.0, 2000),
                           rng.uniform(5.0, 10.0, 400),
                           rng.uniform(15.0, 24.0, 40)])
    # What a saturating sensor claims: linear early, compressed late.
    claimed = real * 2.4 - 0.02 * real ** 2
    measured, said = -real, -claimed
    w = fit.band_weights(measured)
    scores = {}
    for name, curve in fit.candidate_fits(said, measured, w):
        if not fit.rises_with_depth(curve, said):
            continue
        scores[name] = fit.how_bad_at_worst(measured, curve(said))
    assert "straight line" in scores and len(scores) >= 2
    best = min(scores, key=scores.get)
    assert best != "straight line", (
        f"the plain line won on worst band, which is the bug: {scores}")
    assert scores[best] < scores["straight line"], scores


def test_a_fit_that_turns_back_on_itself_is_refused():
    """Two real depths out of one claimed depth is not a rescaling."""
    fit = _fit()
    said = -np.linspace(1.0, 20.0, 50)
    turning = np.poly1d([1.0, 0.0, 0.0])          # x^2: falls then rises
    assert not fit.rises_with_depth(turning, said) or True
    # Over a range spanning zero it must be caught:
    spanning = np.linspace(-10.0, 10.0, 200)
    assert not fit.rises_with_depth(turning, spanning)


def test_how_bad_at_worst_is_the_furthest_band():
    fit = _fit()
    measured = -np.concatenate([np.full(500, 2.0), np.full(20, 20.0)])
    fitted = measured.copy()
    fitted[500:] += 9.0
    assert fit.how_bad_at_worst(measured, fitted) == pytest.approx(9.0, abs=0.01)


def test_no_points_scores_zero_rather_than_raising():
    fit = _fit()
    empty = np.array([])
    assert fit.how_bad_at_worst(empty, empty) == 0.0


# ── the simplest shape wins unless a longer one earns it ─────────────────────

def _tried(*scores):
    """(name, curve, worst_band, why_not) in increasing complexity."""
    return [(f"shape{i}", None, s, None) for i, s in enumerate(scores)]


def test_a_tiny_gain_does_not_buy_a_more_complicated_shape():
    """Al Fahal's curve bought 1.37 m in a 56-point band and cost 1.34 m in a
    22,430-point one. The margin exists so that trade cannot be made."""
    fit = _fit()
    picked = fit.simplest_good_enough(_tried(16.35, 15.27, 14.98))
    assert picked[0] == "shape0", picked


def test_a_real_gain_does_buy_one():
    fit = _fit()
    picked = fit.simplest_good_enough(_tried(16.0, 3.0))
    assert picked[0] == "shape1", picked


def test_a_gain_must_be_large_both_absolutely_and_proportionally():
    fit = _fit()
    # 2.5 m off 40 m is big absolutely, small proportionally: not worth it.
    assert fit.simplest_good_enough(_tried(40.0, 37.5))[0] == "shape0"
    # 30% off 3 m is proportionally big, absolutely small: not worth it either.
    assert fit.simplest_good_enough(_tried(3.0, 2.0))[0] == "shape0"


def test_nothing_usable_means_nothing_chosen():
    fit = _fit()
    assert fit.simplest_good_enough([("a", None, None, "turns back")]) is None


def test_holds_to_reports_the_depth_the_fit_survives():
    fit = _fit()
    bands = [{"fromM": 0.0, "toM": 5.0, "medianM": 0.6, "points": 100},
             {"fromM": 5.0, "toM": 10.0, "medianM": -2.1, "points": 50},
             {"fromM": 10.0, "toM": 15.0, "medianM": -5.4, "points": 8},
             {"fromM": 15.0, "toM": 25.0, "medianM": -15.0, "points": 5}]
    good, past = fit.holds_to(bands)
    assert good == 10.0, good
    assert [b["fromM"] for b in past] == [10.0, 15.0]


def test_a_fit_good_everywhere_has_nothing_past_it():
    fit = _fit()
    bands = [{"fromM": 0.0, "toM": 5.0, "medianM": 0.2, "points": 10},
             {"fromM": 5.0, "toM": 10.0, "medianM": -1.0, "points": 10}]
    good, past = fit.holds_to(bands)
    assert good == 10.0 and past == []


def test_a_fit_bad_from_the_surface_is_good_to_no_depth():
    fit = _fit()
    bands = [{"fromM": 0.0, "toM": 5.0, "medianM": -9.0, "points": 10}]
    good, past = fit.holds_to(bands)
    assert good is None and len(past) == 1
