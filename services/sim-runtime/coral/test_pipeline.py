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
