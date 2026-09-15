"""A task pointed at something somebody drew.

Until now a task carried its own geometry as offsets from wherever the vehicle
happened to start, because there was nowhere else for geometry to live: "survey
the plot" meant "survey a sixty-metre box ahead of you and hope somebody aimed
the vehicle". A plot is now a thing with corners on a chart, and a task can be
pointed at it.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import task_for  # noqa: E402
from world import World  # noqa: E402


def a_site() -> World:
    return World({"things": [
        {"id": "cell-b7", "kind": "restoration-cell", "x": 100.0, "y": 50.0,
         "groundM": 9.0,
         "corners": [{"x": 70.0, "y": 30.0}, {"x": 130.0, "y": 30.0},
                     {"x": 130.0, "y": 70.0}, {"x": 70.0, "y": 70.0}]},
        {"id": "frame-3", "kind": "nursery-frame", "x": 105.0, "y": 60.0,
         "groundM": 8.0, "z": -8.0},
    ]})


def test_a_survey_over_a_plot_covers_the_plot_and_not_a_box_ahead_of_the_vehicle():
    world = a_site()
    started = np.array([0.0, 0.0, -6.0])
    survey = task_for({"kind": "survey", "over": "cell-b7", "altitudeM": 2.0},
                      started, 0.0, world=world)
    assert (survey.width, survey.height) == (60.0, 40.0), "the plot's own extent"
    # The corner it counts from is the plot's north-west corner, so a pose in
    # the middle of the plot is in the middle of the box.
    assert survey.began_at[0] == 70.0 and survey.began_at[1] == 70.0
    survey.judge(1.0, np.array([100.0, 50.0, -7.0]), 0.0, -9.0)
    assert survey.detail()["fractionSeen"] > 0.0, "the middle of the plot counts"
    # And a pose sixty metres ahead of where the *vehicle* started, which is
    # what the old geometry would have scored, counts for nothing.
    before = survey.detail()["fractionSeen"]
    survey.judge(2.0, np.array([30.0, 0.0, -7.0]), 0.0, -9.0)
    assert survey.detail()["fractionSeen"] == before


def test_a_result_names_what_it_was_pointed_at():
    world = a_site()
    survey = task_for({"kind": "survey", "over": "cell-b7"},
                      np.array([0.0, 0.0, -6.0]), 0.0, world=world)
    said = survey.result()["over"]
    assert said["id"] == "cell-b7" and said["kind"] == "restoration-cell"
    assert said["is"] == "a plot somebody works inside"


def test_a_point_may_be_a_thing_somebody_drew():
    """"Go to that frame" is what a person means when they point at a chart."""
    world = a_site()
    reach = task_for({"kind": "reach", "target": {"over": "frame-3"}},
                     np.array([0.0, 0.0, -6.0]), 0.0, world=world)
    assert list(reach.target) == [105.0, 60.0, -8.0]


def test_pointing_at_something_that_is_not_there_says_so():
    """It would otherwise fall back to a box ahead of the vehicle and come back
    as a mediocre score, which reads as a controller that flew badly."""
    survey = task_for({"kind": "survey", "over": "cell-b8"},
                      np.array([0.0, 0.0, -6.0]), 0.0, world=a_site())
    assert survey.missing == "cell-b8"
    assert survey.result()["pointedAtNothing"] == "cell-b8"


def test_a_task_pointed_at_nothing_in_a_dive_with_no_layout_says_so_too():
    survey = task_for({"kind": "survey", "over": "cell-b7"},
                      np.array([0.0, 0.0, -6.0]), 0.0)
    assert survey.missing == "cell-b7"


def test_a_task_that_points_at_nothing_is_unchanged():
    """The whole point of the step: the existing forms keep working."""
    plain = task_for({"kind": "survey", "widthM": 20.0, "heightM": 10.0},
                     np.array([5.0, 5.0, -6.0]), 0.0)
    assert plain.over is None and plain.missing == ""
    assert (plain.width, plain.height) == (20.0, 10.0)
    assert list(plain.began_at) == [5.0, 5.0, -6.0]
    assert "over" not in plain.result()


def test_any_task_pointed_at_a_thing_aims_at_it():
    """"Inspect, over frame-3" names a place as plainly as a pair of numbers.

    It used to depend on the task: a reach fell back to the objective itself
    and found `over` there, an inspect asked only for `target` and found
    nothing — so a stage a person wrote the same way in an editor meant one
    thing for one task and nothing at all for the next.
    """
    world = a_site()
    where = [105.0, 60.0, -8.0]
    for kind in ("reach", "inspect", "revisit", "dock"):
        pointed = task_for({"kind": kind, "over": "frame-3"},
                           np.array([0.0, 0.0, -6.0]), 0.0, world=world)
        if pointed is None or not hasattr(pointed, "target"):
            continue
        assert list(pointed.target) == where, f"{kind} did not aim at what it was pointed at"


def test_pointing_a_survey_at_a_plot_still_takes_the_plot_not_its_middle():
    """The one that is not a point: a survey over a plot covers the plot."""
    survey = task_for({"kind": "survey", "over": "cell-b7"},
                      np.array([0.0, 0.0, -6.0]), 0.0, world=a_site())
    assert (survey.width, survey.height) == (60.0, 40.0)
