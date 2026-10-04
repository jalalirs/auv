"""What is drawn on the chart is what is flown: a route's points and a
survey's rectangle given in the place's own frame, whatever the dive began
at and whichever way it was facing."""

from __future__ import annotations

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tasks import task_for  # noqa: E402


def test_a_drawn_route_is_where_it_was_drawn_not_ahead_of_the_start():
    began, heading = np.array([5.0, -3.0, -10.0]), 1.2
    task = task_for({"kind": "waypoints", "points": [{"x": 20.0, "y": 4.0, "depthM": 6.0},
                                                     {"dx": 2.0, "dy": 0.0}]}, began, heading)
    assert np.allclose(task.points[0], [20.0, 4.0, -6.0])
    ahead = np.array([np.cos(heading), np.sin(heading)])
    assert np.allclose(task.points[1][:2], began[:2] + 2.0 * ahead)


def test_a_drawn_survey_covers_its_rectangle():
    task = task_for({"kind": "survey", "altitudeM": 2.0,
                     "area": [{"x": 10, "y": 0}, {"x": 30, "y": 0}, {"x": 30, "y": 8}, {"x": 10, "y": 8}]},
                    np.array([0.0, 0.0, -10.0]), 2.0)
    assert (task.width, task.height) == (20.0, 8.0)
    corners = task.geometry()["rectangle"]
    xs, ys = [c["x"] for c in corners], [c["y"] for c in corners]
    assert (min(xs), max(xs), min(ys), max(ys)) == (10.0, 30.0, 0.0, 8.0)


def test_a_drawn_transect_is_its_line_from_wherever_the_leg_begins():
    task = task_for({"kind": "transect", "altitudeM": 2.0,
                     "from": {"x": 0.0, "y": 10.0}, "to": {"x": 30.0, "y": 50.0}},
                    np.array([-20.0, -20.0, -10.0]), 0.3)
    assert abs(task.length - 50.0) < 1e-9
    goal = task.goal()
    assert goal["from"] == [0.0, 10.0] and goal["to"] == [30.0, 50.0]
