"""A stage of a mission is measured from where the stage began.

`Reach` has carried a comment about this for months: in a mission, where
the dive began and where this leg begins are not the same place, and
scoring a leg on the dive's start makes a leg back to where you began look
like a leg to nowhere. A transect did not carry that fix, and nothing
noticed because until there was a mission with more than one stage in it
the two were always the same place.
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tasks import task_for  # noqa: E402

FLOOR = -20.0


def fly(task, path, *, floor=FLOOR, heading=0.0, dt=1.0):
    for n, where in enumerate(path):
        task.step(n * dt, np.array(where, dtype=float), heading, floor, [0.1] * 6)
    return task


def test_a_transect_flown_on_its_own_is_unchanged():
    """The fix must be a no-op for a dive of one stage, which is every dive
    already in the record."""
    task = task_for({"kind": "transect", "lengthM": 10.0, "altitudeM": 2.0,
                     "altitudeBandM": 0.5},
                    began_at=(0.0, 0.0, FLOOR + 2.0), heading=0.0)
    fly(task, [(x, 0.0, FLOOR + 2.0) for x in range(12)])
    assert task.detail()["goodM"] == pytest.approx(10.0)
    assert task.score() == pytest.approx(1.0)


def test_a_transect_after_another_leg_measures_from_where_it_started():
    """The bug: after a leg that had already run along the line, `along`
    began at some positive number, the transect ended at once, and it
    scored zero for a reason that had nothing to do with the flying."""
    # The dive began at the origin; this leg begins 40 m along, which is
    # what a mission's earlier stage would have done.
    task = task_for({"kind": "transect", "lengthM": 10.0, "altitudeM": 2.0,
                     "altitudeBandM": 0.5},
                    began_at=(0.0, 0.0, FLOOR + 2.0), heading=0.0)
    fly(task, [(40.0 + x, 0.0, FLOOR + 2.0) for x in range(12)])
    assert task.detail()["alongM"] == pytest.approx(10.0)
    assert task.score() == pytest.approx(1.0), task.detail()


def test_an_unstated_heading_is_the_one_the_leg_starts_on():
    """A transect that follows a descent runs along the heading the vehicle
    has when it gets there, not the one the dive was launched on."""
    task = task_for({"kind": "transect", "lengthM": 10.0, "altitudeM": 2.0,
                     "altitudeBandM": 0.5},
                    began_at=(0.0, 0.0, FLOOR + 2.0), heading=0.0)
    # Pointing north, flying north, while the dive began pointing east.
    fly(task, [(0.0, y, FLOOR + 2.0) for y in range(12)], heading=math.pi / 2)
    assert task.score() == pytest.approx(1.0)


def test_a_stated_heading_is_obeyed_whatever_the_vehicle_is_doing():
    task = task_for({"kind": "transect", "lengthM": 10.0, "altitudeM": 2.0,
                     "altitudeBandM": 0.5, "headingDeg": 0.0,
                     "headingToleranceDeg": 10.0},
                    began_at=(0.0, 0.0, FLOOR + 2.0), heading=0.0)
    # Told to run along the dive's heading; flown north instead.
    fly(task, [(0.0, y, FLOOR + 2.0) for y in range(12)], heading=math.pi / 2)
    assert task.score() == pytest.approx(0.0)


def test_the_line_it_draws_is_the_line_it_scored():
    """A chart that draws the transect somewhere the vehicle never went is
    a chart of a different dive."""
    task = task_for({"kind": "transect", "lengthM": 10.0},
                    began_at=(0.0, 0.0, FLOOR + 2.0), heading=0.0)
    fly(task, [(40.0 + x, 0.0, FLOOR + 2.0) for x in range(4)])
    line = task.geometry()["line"]
    assert line[0]["x"] == pytest.approx(40.0)
    assert line[1]["x"] == pytest.approx(50.0)


def test_a_whole_dive_runs_its_stages_in_order():
    """descend, transect, return — the mission this all exists for."""
    task = task_for({"kind": "mission", "stages": [
        {"kind": "descend", "toAltitudeM": 2.0, "bandM": 0.5, "timeLimitS": 60},
        {"kind": "transect", "lengthM": 10.0, "altitudeM": 2.0,
         "altitudeBandM": 0.6, "timeLimitS": 60},
        {"kind": "return", "homeRadiusM": 3.0, "surfaceDepthM": 0.5,
         "timeLimitS": 60},
    ]}, began_at=(0.0, 0.0, -1.0), heading=0.0)
    assert [one.kind for one in task.stages] == ["descend", "transect", "return"]

    t = 0.0
    def step(where, heading=0.0):
        nonlocal t
        task.step(t, np.array(where, dtype=float), heading, FLOOR, [0.1] * 6,
                  locked=(where[2] - FLOOR) <= 50.0)
        t += 1.0

    for z in np.arange(-1.0, FLOOR + 2.0, -1.0):      # down
        step((0.0, 0.0, float(z)))
    step((0.0, 0.0, FLOOR + 2.0))
    assert task.stages[0].detail()["arrived"] is True, task.stages[0].detail()
    for x in range(12):                                # along
        step((float(x), 0.0, FLOOR + 2.0))
    for x in range(11, -1, -1):                        # home
        step((float(x), 0.0, FLOOR + 2.0))
    for z in np.arange(FLOOR + 2.0, 0.0, 1.0):         # up
        step((0.0, 0.0, float(z)))
    step((0.0, 0.0, -0.2))
    assert task.done, task.progress()
    kinds = [one["kind"] for one in task.result()["achieved"]["stages"]]
    assert kinds == ["descend", "transect", "return"], task.result()["achieved"]
    assert task.result()["achieved"]["stopped"] is False


# ── the recovery ─────────────────────────────────────────────────────────────
#
# Coming up is the descent's mirror and the half nobody writes down. An
# untethered vehicle cannot hold station while it rises, so the water takes
# it, and where it breaks the surface decides whether the boat has to go
# looking.

def a_return(**asked):
    return task_for({"kind": "return", "homeRadiusM": 3.0, "surfaceDepthM": 0.5,
                     **asked}, began_at=(0.0, 0.0, -18.0), heading=0.0)


def test_a_return_reports_where_it_surfaced_and_how_far_the_water_took_it():
    task = a_return()
    # Rises from 18 m, set 2 m sideways each step by the current.
    fly(task, [(2.0 * n, 0.0, -18.0 + 2.0 * n) for n in range(10)])
    said = task.detail()
    assert said["roseFromM"] == pytest.approx(18.0)
    assert said["surfacedOffM"] == pytest.approx(18.0)
    assert said["driftedWhileRisingM"] == pytest.approx(18.0)


def test_it_says_how_fast_it_came_up():
    task = a_return()
    fly(task, [(0.0, 0.0, -18.0 + 3.0 * n) for n in range(8)])
    assert task.detail()["worstRateMs"] == pytest.approx(3.0)


def test_what_a_return_is_worth_has_not_moved():
    """Getting home and surfacing is the job. The recovery is reported, not
    scored — every return already in the record must mean what it meant."""
    got_home = a_return()
    fly(got_home, [(0.0, 0.0, -18.0 + 2.0 * n) for n in range(10)])
    assert got_home.score() == pytest.approx(1.0)
    assert got_home.detail()["surfaced"] is True

    drifted = a_return()
    fly(drifted, [(20.0, 0.0, -18.0 + 2.0 * n) for n in range(10)])
    # Surfaced, but nowhere near home: half marks, as before.
    assert drifted.score() == pytest.approx(0.0)
    assert drifted.detail()["surfacedOffM"] == pytest.approx(20.0)
