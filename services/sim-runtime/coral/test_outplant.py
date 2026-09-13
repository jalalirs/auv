"""Planting corals where the plan said, and finding out where they went.

The task that asks this platform's question hardest: the vehicle plants where
it *believes* the mark is, and the coral ends up where the vehicle *actually*
is. Nothing fails when navigation is bad — the manipulator works, the coral
goes in, the log says done — and the colony is metres from where it was meant
to be.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import task_for  # noqa: E402


def a_task(**objective):
    said = {"kind": "outplant", "cell": {"widthM": 4.0, "heightM": 2.0, "spacingM": 2.0},
            "placeM": 0.5, "toleranceM": 1.0, "altitudeM": 1.0, "altitudeBandM": 0.5,
            "speedMs": 0.2, "holdS": 2.0, "timeLimitS": 600.0}
    said.update(objective)
    return task_for(said, np.array([0.0, 0.0, -10.0]), 0.0)


def plant_at(task, mark, offset=(0.0, 0.0), t0=0.0):
    """Sit over a mark for long enough to get a coral in the ground.

    `offset` is how far the vehicle really is from where it believes it is —
    the navigation error, applied the way the water applies it: belief goes to
    the mark, truth lands somewhere else.
    """
    believed = np.array([mark[0], mark[1], -10.0])
    truth = np.array([mark[0] + offset[0], mark[1] + offset[1], -10.0])
    for i in range(4):
        task.step(t0 + i, truth, 0.0, truth[2] - 1.0, [0.0], believed=believed)
    return t0 + 4


def test_a_grid_is_laid_out_the_way_a_cell_is_worked():
    task = a_task()
    assert len(task.marks) == 6, "3 columns x 2 rows at 2 m spacing"
    # Boustrophedon: the second row runs back the other way, because that is
    # how you work a cell rather than flying back to the start of every row.
    assert task.marks[0][0] == 0.0 and task.marks[2][0] == 4.0
    assert task.marks[3][0] == 4.0 and task.marks[5][0] == 0.0


def test_perfect_navigation_plants_on_the_mark():
    task = a_task()
    t = 0.0
    for mark in list(task.marks):
        t = plant_at(task, mark, offset=(0.0, 0.0), t0=t)
    assert task.done
    assert task.score() == 1.0
    assert task.detail()["planted"] == 6
    assert task.detail()["onTheMark"] == 6
    assert task.detail()["meanErrorM"] == 0.0


def test_a_drifting_vehicle_plants_everything_and_gets_none_of_it_right():
    """The whole point. Every coral goes in the ground; none is where it should be.

    Nothing about this looks like a failure from the vehicle's side: it
    believed it was on every mark, it held station, it planted, and its own log
    says six of six. Only the truth says the reef is three metres from the plan.
    """
    task = a_task()
    t = 0.0
    for mark in list(task.marks):
        t = plant_at(task, mark, offset=(3.0, 0.0), t0=t)
    assert task.detail()["planted"] == 6, "it planted all of them"
    assert task.detail()["onTheMark"] == 0, "and not one is where it was meant to be"
    assert task.score() == 0.0
    assert abs(task.detail()["meanErrorM"] - 3.0) < 1e-6
    assert task.failed()


def test_where_every_coral_actually_went_is_kept():
    """A restoration has to be able to go back and find what it planted."""
    task = a_task()
    plant_at(task, task.marks[0], offset=(1.5, -0.5))
    went = task.detail()["wentTo"]
    assert len(went) == 1
    assert went[0] == [round(float(task.marks[0][0] + 1.5), 2),
                       round(float(task.marks[0][1] - 0.5), 2)]


def test_it_will_not_plant_from_too_high_or_too_fast():
    """A manipulator needs the vehicle low and still, and so does this."""
    task = a_task()
    mark = task.marks[0]
    believed = np.array([mark[0], mark[1], -10.0])
    # Right over the mark, but three metres up.
    for i in range(6):
        task.step(float(i), believed, 0.0, believed[2] - 3.0, [0.0], believed=believed)
    assert task.detail()["planted"] == 0, "too high to plant"

    # Low enough now, but moving a metre a second.
    task = a_task()
    for i in range(6):
        truth = np.array([mark[0] + i * 1.0, mark[1], -10.0])
        task.step(float(i), truth, 0.0, truth[2] - 1.0, [0.0],
                  believed=np.array([mark[0], mark[1], -10.0]))
    assert task.detail()["planted"] == 0, "too fast to plant"


def test_a_task_with_nowhere_to_plant_says_so_rather_than_inventing_a_grid():
    task = task_for({"kind": "outplant"}, np.array([0.0, 0.0, -10.0]), 0.0)
    assert task.marks == []
    assert task.score() == 0.0
    assert task.says() == "nowhere to plant"


def test_the_plan_carries_the_height_the_work_needs():
    """A planting task has to be near the bottom, and the plan must say so.

    The marks of a working task are laid out on a chart, so the depth they
    carry is whatever the vehicle happened to start at. Flown as a depth over a
    seabed that slopes away, the vehicle arrives above every mark, holds
    station at each one exactly as asked, and plants nothing — which is what it
    did over a real reef for forty minutes.
    """
    import sys, pathlib as _p
    sys.path.insert(0, str(_p.Path(__file__).resolve().parent / "controllers"))
    from controllers import plan as planner

    task = a_task()
    goal = task.goal()
    assert goal["altitudeM"] == task.altitude, "the goal knows the work needs height"
    legs = planner.route_for(goal)
    assert legs, "it should plan something"
    for leg in legs:
        assert leg.get("altitudeM") == task.altitude, leg
        assert "depthM" not in leg, "a depth here is the bug: the bottom moves"
