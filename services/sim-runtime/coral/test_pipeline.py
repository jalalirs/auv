"""A pipeline on the seabed: where it rests, where it spans, and its inspection."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import task_for  # noqa: E402
from world import Laid, Thing, World  # noqa: E402


def a_hollow(x, y):
    """Flat sand at 20 m with a hollow a metre deep and twenty across at x = 50."""
    return -20.0 - (1.0 if abs(x - 50.0) < 10.0 else 0.0)


def a_pipe(bend=150.0):
    return Thing.of({"id": "pipe-1", "kind": "pipeline", "bendRadiusM": bend,
                     "route": [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}]})


def test_a_pipeline_is_laid_on_the_bottom():
    pipe = a_pipe()
    assert isinstance(pipe, Laid)
    pipe.lay(lambda x, y: -20.0)
    z = np.array([p[2] for p in pipe.curve])
    assert np.allclose(z, -20.0 + pipe.radius)
    assert pipe.spans == []


def test_it_bridges_a_hollow_as_a_free_span():
    pipe = a_pipe()
    pipe.lay(a_hollow)
    assert len(pipe.spans) == 1
    span = pipe.spans[0]
    # A stiff pipe does not follow a hollow it is too stiff to bend into.
    assert span["lengthM"] >= 15.0
    assert 0.5 < span["mostGapM"] <= 1.0
    assert 40.0 < span["x"] < 60.0


def test_a_limp_line_follows_the_hollow_closer():
    stiff, limp = a_pipe(bend=500.0), a_pipe(bend=5.0)
    stiff.lay(a_hollow)
    limp.lay(a_hollow)
    assert (max((s["mostGapM"] for s in limp.spans), default=0.0)
            < max(s["mostGapM"] for s in stiff.spans))


def test_the_world_lays_it_once_it_knows_the_bottom():
    world = World({"things": [{"id": "pipe-1", "kind": "pipeline",
                               "route": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]}]})
    world.on_this_seabed(a_hollow)
    assert world.by_id("pipe-1").spans


def test_following_it_sees_the_line_and_the_span():
    world = World({"things": [{"id": "pipe-1", "kind": "pipeline",
                               "route": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]}]})
    world.on_this_seabed(a_hollow)
    task = task_for({"kind": "follow", "over": "pipe-1", "altitudeM": 2.0, "swathM": 3.0},
                    np.array([0.0, 0.0, -17.0]), 0.0, world=world)
    assert task.goal()["kind"] == "visit" and len(task.goal()["points"]) >= 10
    # Flown along it at two metres over the pipe.
    for k, x in enumerate(np.arange(0.0, 100.5, 0.5)):
        pipe_z = np.interp(x, task.line[:, 0], task.line[:, 2])
        task.step(float(k), np.array([x, 0.0, pipe_z + 2.0]), 0.0, -20.0, np.zeros(1))
    assert task.seen_m() > 99.0
    assert all(one["seen"] for one in task.spans_seen())
    assert task.score() > 0.99


def test_flying_beside_it_out_of_view_sees_nothing():
    world = World({"things": [{"id": "pipe-1", "kind": "pipeline",
                               "route": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]}]})
    world.on_this_seabed(a_hollow)
    task = task_for({"kind": "follow", "over": "pipe-1", "altitudeM": 2.0, "swathM": 3.0},
                    np.array([0.0, 0.0, -17.0]), 0.0, world=world)
    for k, x in enumerate(np.arange(0.0, 100.5, 0.5)):
        task.step(float(k), np.array([x, 10.0, -18.0]), 0.0, -20.0, np.zeros(1))
    assert task.seen_m() == 0.0 and task.score() == 0.0


def test_it_is_followed_at_its_own_height_plus_the_altitude():
    """The route rides the line: each point the altitude above the pipe there,
    not an altitude over whatever the altimeter sees."""
    from tasks import task_for

    world = World({"things": [{"id": "pipe-1", "kind": "pipeline",
                               "route": [{"x": 0, "y": 0}, {"x": 60, "y": 0}]}]})
    world.on_this_seabed(lambda x, y: -10.0 - 0.1 * x)
    task = task_for({"kind": "follow", "over": "pipe-1", "altitudeM": 3.0, "swathM": 3.0},
                    np.array([0.0, 0.0, -2.0]), 0.0, world=world)
    goal = task.goal()
    assert "altitudeM" not in goal
    for x, y, z in goal["points"]:
        k = int(np.argmin(np.hypot(task.line[:, 0] - x, task.line[:, 1] - y)))
        assert abs(z - (task.line[k, 2] + 3.0)) < 1e-9


def fly(task, start, speed=0.5, steps=1200):
    """A vehicle that flies at the task's goal points and is told again when
    the goal changes, as the runtime's planner is (systems/tasking.py)."""
    here, flying, points, k = np.array(start, dtype=float), None, [], 0
    for t in range(steps):
        if task.goal_id() != flying:
            flying, points, k = task.goal_id(), task.goal()["points"], 0
        if k < len(points):
            to = np.array(points[k]) - here
            gap = float(np.linalg.norm(to))
            if gap <= speed:
                here, k = np.array(points[k], dtype=float), k + 1
            else:
                here = here + to / gap * speed
        task.step(float(t), here, 0.0, -20.0, np.zeros(1), believed=here)
        if task.done:
            break
    return task


def a_found_pipe(**said):
    world = World({"things": [{"id": "pipe-1", "kind": "pipeline", "shownBy": "reconstruction",
                               "route": [{"x": 0, "y": 0}, {"x": 150, "y": 0}],
                               "exposed": [{"fromM": 0, "toM": 90}],
                               "features": [{"id": f"block-{n}", "what": "concrete block", "atM": 10.0 * n + 1}
                                            for n in range(8)], **said}]})
    world.on_this_seabed(lambda x, y: -17.0)
    return world


def test_a_pipe_knows_where_it_is_out_of_the_sand():
    pipe = a_found_pipe().by_id("pipe-1")
    assert pipe.is_exposed(40.0) and not pipe.is_exposed(120.0)
    assert pipe.described()["exposedM"] == 90.0 and pipe.described()["features"] == 8


def test_a_chart_three_metres_off_is_found_by_sweeping_and_corrected():
    task = task_for({"kind": "follow", "over": "pipe-1", "altitudeM": 2.5, "altitudeBandM": 1.0,
                     "swathM": 3.0, "chartErrorM": [0.0, 3.0], "searchM": 5.0, "timeLimitS": 3000},
                    np.array([-5.0, 3.0, -14.5]), 0.0, world=a_found_pipe())
    fly(task, [-5.0, 3.0, -14.5])
    said = task.detail()
    assert said["acquired"] is not None and said["acquired"]["alongM"] < 45.0
    # It moved its line onto the pipe: within half a metre of where it is.
    assert abs(said["chartOffM"]["value"][1] + 3.0) < 0.5
    assert said["replanned"] >= 1
    # The exposed run it reports ends where the pipe goes under, give or take.
    runs = said["seenExposed"]
    assert runs and 85.0 <= runs[-1]["toM"] <= 91.0
    found = [one for one in said["features"] if one["found"]]
    assert len(found) >= 4
    assert task.score() > 0.5


def test_flying_the_wrong_chart_without_sweeping_sees_nothing():
    task = task_for({"kind": "follow", "over": "pipe-1", "altitudeM": 2.5, "altitudeBandM": 1.0,
                     "swathM": 3.0, "chartErrorM": [0.0, 3.0], "timeLimitS": 3000},
                    np.array([-5.0, 3.0, -14.5]), 0.0, world=a_found_pipe())
    fly(task, [-5.0, 3.0, -14.5])
    assert task.detail()["acquired"] is None and task.score() == 0.0


def test_a_pipe_shown_by_its_reconstruction_is_not_drawn_again():
    pipe = a_found_pipe().by_id("pipe-1")
    assert pipe.shown_by == "reconstruction"
