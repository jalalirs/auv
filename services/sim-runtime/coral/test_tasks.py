"""Tasks judge trajectories; these hand them trajectories and check the judgement."""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import KINDS, task_for  # noqa: E402

START = np.array([100.0, -20.0, -5.0])


def walk(task, seconds, where, heading=0.0, floor=None, dt=0.05):
    """Hand the task a trajectory for a while. `where` sees the time since this
    walk began; the task's clock keeps running across walks, as a dive's does."""
    began = getattr(task, "_clock", 0.0)
    steps = int(round(seconds / dt))
    for k in range(steps + 1):
        local = k * dt
        task.step(began + local, where(local), heading, floor(local) if callable(floor) else floor, [0.1] * 6)
    task._clock = began + steps * dt
    return task


def test_every_kind_is_known():
    for kind in KINDS:
        task = task_for({"kind": kind}, START, 0.0)
        assert task is not None, kind
    assert task_for({}, START, 0.0) is None
    assert task_for({"kind": "juggle"}, START, 0.0) is None


def test_hold_station_scores_the_time_on_station():
    task = task_for({"kind": "hold-station", "seconds": 20, "radiusM": 0.5, "depthBandM": 0.3}, START, 0.0)
    # Half the time on station, half a metre and a half off.
    walk(task, 20, lambda t: START if t < 10 else START + np.array([1.5, 0, 0]))
    assert task.done
    assert 0.45 <= task.score() <= 0.55, task.progress()
    result = task.result()
    assert result["achieved"]["worstOffM"] == 1.5
    assert result["thrusterEffort"] == 0.1


def test_waypoints_are_reached_in_order():
    task = task_for({"kind": "waypoints", "radiusM": 1.0, "timeLimitS": 100,
                     "points": [{"dx": 5, "dy": 0}, {"dx": 5, "dy": 5}]}, START, 0.0)
    # Straight to the second point first: it does not count until the first is
    # reached. dy is to starboard, which for a heading of east is south.
    walk(task, 5, lambda t: START + np.array([5, -5, 0]))
    assert task.reached == 0
    walk(task, 5, lambda t: START + np.array([5, 0, 0]))
    assert task.reached == 1
    walk(task, 5, lambda t: START + np.array([5, -5, 0]))
    assert task.reached == 2 and task.done and task.score() == 1.0
    geometry = task.geometry()
    assert len(geometry["points"]) == 2 and geometry["points"][0]["x"] == 105.0


def test_waypoints_relative_to_the_heading():
    task = task_for({"kind": "waypoints", "points": [{"dx": 10, "dy": 0}]}, START, math.radians(90))
    point = task.points[0]
    assert abs(point[0] - START[0]) < 1e-9 and abs(point[1] - (START[1] + 10)) < 1e-9  # north, ten metres


def test_transect_counts_length_flown_in_band_on_heading():
    task = task_for({"kind": "transect", "lengthM": 20, "altitudeM": 2.0, "altitudeBandM": 0.5,
                     "headingToleranceDeg": 10}, START, 0.0)
    floor = -7.0  # two metres under a vehicle at -5
    # First half at altitude, second half a metre too high.
    walk(task, 10, lambda t: START + np.array([t * 2.0, 0, 0 if t < 5 else 1.0]), heading=0.0, floor=floor)
    assert task.done, task.progress()
    assert 0.45 <= task.score() <= 0.55, task.progress()


def test_survey_scores_the_fraction_seen():
    task = task_for({"kind": "survey", "widthM": 10, "heightM": 6, "altitudeM": 2.0, "swathM": 3.0}, START, 0.0)
    # Two passes three metres apart cover a six-metre-tall rectangle.
    def where(t):
        if t < 10:
            return START + np.array([t, -1.5, 0])
        return START + np.array([20 - t, -4.5, 0])
    walk(task, 20, where, floor=-7.0)
    assert task.score() > 0.95, task.progress()
    assert task.done


def test_return_is_home_and_surfaced():
    task = task_for({"kind": "return", "homeRadiusM": 2.0, "surfaceDepthM": 0.5}, START, 0.0)
    walk(task, 5, lambda t: START + np.array([10, 0, 0]))
    assert task.score() == 0.0
    walk(task, 5, lambda t: START)
    assert task.score() == 0.5 and not task.done
    walk(task, 5, lambda t: np.array([START[0], START[1], -0.2]))
    assert task.score() == 1.0 and task.done


def test_inspect_says_why_it_cannot_be_judged():
    task = task_for({"kind": "inspect"}, START, 0.0)
    assert task.done and "structure" in task.says()
