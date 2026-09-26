"""Getting down to the bottom, on the site, under control.

The phase of a dive nobody had modelled and the one an operator spends the
most breath on. A vehicle enters the water above the site and has to arrive
at working altitude *over the site*, and between those two moments it is
being set sideways by whatever the current is doing and cannot see the
bottom to know.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tasks import TASKS, task_for  # noqa: E402


FLOOR = -40.0


def a_descent(**asked):
    return task_for({"kind": "descend", **asked}, began_at=(0.0, 0.0, -1.0), heading=0.0)


def fly(task, path, *, locked_below=50.0, floor=FLOOR, dt=1.0):
    """Fly a list of positions past the task, a second apart.

    `locked_below` is the altitude at which the Doppler log finds the bottom,
    which is the navigation's answer and is handed down rather than worked
    out by the task.
    """
    for n, where in enumerate(path):
        at = np.array(where, dtype=float)
        altitude = float(at[2] - floor)
        task.step(n * dt, at, 0.0, floor, [0.1] * 6, locked=altitude <= locked_below)
    return task


def test_it_is_a_task_anybody_can_ask_for():
    assert "descend" in TASKS
    assert a_descent().kind == "descend"


def test_arriving_at_the_altitude_it_was_told():
    task = a_descent(toAltitudeM=3.0, bandM=0.5)
    fly(task, [(0, 0, -1 - 4 * n) for n in range(10)])
    assert task.detail()["arrived"] is True
    assert task.done and not task.failed()


def test_a_descent_that_never_gets_down_fails_and_says_how_far_it_got():
    task = a_descent(toAltitudeM=3.0, timeLimitS=5)
    fly(task, [(0, 0, -1 - n) for n in range(8)])
    assert task.failed()
    # Credit for the water column it did get through, so a vehicle that
    # stopped part way and one that never left the surface differ.
    assert 0.0 < task.score() < 0.5


def test_where_it_landed_is_most_of_what_is_left_of_the_score():
    """A descent is a drift problem: a tenth of a knot over a hundred metres
    of water column is twenty metres downstream, and the site is forty
    metres across."""
    on = a_descent(toAltitudeM=3.0, withinM=5.0)
    fly(on, [(0, 0, -1 - 4 * n) for n in range(10)])
    off = a_descent(toAltitudeM=3.0, withinM=5.0)
    fly(off, [(2.0 * n, 0, -1 - 4 * n) for n in range(10)])
    assert on.score() > off.score()
    assert off.detail()["offTheMarkM"] > 5.0


def test_a_vehicle_that_arrives_by_falling_arrives_badly():
    """It stirs the bottom it came to photograph, and a manipulator wants a
    hull that is already still."""
    gentle = a_descent(toAltitudeM=3.0, rateMs=0.4)
    fly(gentle, [(0, 0, -1 - 0.3 * n) for n in range(140)])
    fast = a_descent(toAltitudeM=3.0, rateMs=0.4)
    fly(fast, [(0, 0, -1 - 4.0 * n) for n in range(10)])
    assert gentle.detail()["arrived"] and fast.detail()["arrived"]
    assert gentle.score() > fast.score()
    assert fast.detail()["rateOnArrivalMs"] > 0.4


def test_it_reports_how_much_of_the_descent_was_flown_blind():
    """The fact the rest of the dive's navigation rests on. A Doppler log has
    a range, and above it there is no bottom track at all."""
    task = a_descent(toAltitudeM=3.0)
    # Enters at 1 m, floor at 40 m, log finds the bottom at 20 m altitude —
    # that is 20 m down, and the vehicle is set 1 m sideways each step.
    fly(task, [(1.0 * n, 0, -1 - 2.0 * n) for n in range(20)], locked_below=20.0)
    said = task.detail()
    assert said["bottomLock"] is True
    assert said["lockedAtAltitudeM"] == pytest.approx(19.0)
    assert said["blindThroughM"] == pytest.approx(20.0)
    # And how far the water had carried it in those metres.
    assert said["driftedWhileBlindM"] == pytest.approx(10.0)


def test_a_vehicle_with_no_log_says_it_never_had_the_bottom():
    task = a_descent(toAltitudeM=3.0)
    fly(task, [(0, 0, -1 - 4 * n) for n in range(10)], locked_below=-1.0)
    said = task.detail()
    assert said["bottomLock"] is False
    assert said["blindThroughM"] is None
    assert said["driftedWhileBlindM"] is None


def test_nobody_saying_is_not_the_same_as_no_lock():
    """A task flown by something that does not pass the log's state must not
    report that the log failed."""
    task = a_descent(toAltitudeM=3.0)
    for n in range(10):
        task.step(n, np.array([0.0, 0.0, -1 - 4.0 * n]), 0.0, FLOOR, [0.1] * 6)
    assert task.locked is None
    assert task.detail()["bottomLock"] is False
    assert task.detail()["blindThroughM"] is None


def test_it_can_be_told_a_depth_when_there_is_no_bottom_to_speak_of():
    task = a_descent(toDepthM=25.0, bandM=1.0)
    fly(task, [(0, 0, -1 - 3.0 * n) for n in range(12)], floor=-400.0)
    assert task.detail()["arrived"] is True
    assert task.detail()["toAltitudeM"] is None


def test_a_descent_that_missed_stops_a_mission():
    """Everything after it assumes a vehicle that is down."""
    assert a_descent().stops_a_mission is True


def test_the_goal_is_stated_in_the_world_and_not_as_a_route():
    task = a_descent(toAltitudeM=2.5, withinM=4.0)
    goal = task.goal()
    assert goal["kind"] == "descend"
    assert goal["altitudeM"] == 2.5 and goal["withinM"] == 4.0
    assert len(goal["over"]) == 2
