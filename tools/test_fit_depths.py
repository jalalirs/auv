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
