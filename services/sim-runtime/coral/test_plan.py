"""A plan is a document: written down, checked, flown, and compared.

What is being protected here is that the document is the real thing rather
than a description of something else. If a plan can be handed to a dive and
flown as given, kept with the recording, and read back later, then a plan
written by a person, emitted by a model, or worked out by the platform are all
the same kind of object — and two of them can be held side by side, which is
the only way one controller is ever compared with another.

Run with plain pytest from services/sim-runtime/coral.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from controllers import plan  # noqa: E402
from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = HERE.parents[2] / "catalog/vehicles/bluerov2/dynamics.json"
START = (0.0, 0.0, -7.0)

A_SURVEY = {"kind": "cover", "corner": [0.0, 0.0], "along": [1.0, 0.0],
            "widthM": 60.0, "heightM": 30.0, "altitudeM": 5.0}


def a_dive(brief: dict) -> Dive:
    model = Hydrodynamics.from_package(PACKAGE)
    body, allocator = Body(model), Allocator(model)
    said: list = []
    dive = Dive({"durationSeconds": 600.0, "initialState": {"positionM": list(START)}, **brief},
                body, allocator, pathlib.Path("nowhere.usda"),
                lambda kind, **d: said.append((kind, d)))
    dive.said = said
    dive.floor = -12.0
    # Placing the vehicle is what begins a task, and placing it needs a scene.
    # Nothing here opens one, so the task is begun by hand — which is what the
    # tank does too, for the same reason.
    if brief.get("objective"):
        dive.begin_task(brief["objective"])
    return dive


def run(dive: Dive, seconds: float) -> None:
    for _ in range(int(seconds / dive.dt)):
        dive.step()


# ── the document ─────────────────────────────────────────────────────────────

def test_a_plan_compiles_to_the_same_flying_as_the_route_it_replaced():
    """The document is a way of writing the path down, not a different path."""
    document = plan.plan_for(A_SURVEY, camera_half_angle=0.41)
    assert plan.legs_of(document) == plan.route_for(A_SURVEY, camera_half_angle=0.41)


def test_a_plan_is_a_graph_and_not_a_list():
    """Written in any order, it flies in the order its transitions say."""
    document = plan.plan_for({"kind": "dock", "station": [40.0, 0.0, -6.0],
                              "facingDeg": 0.0, "approachM": 8.0})
    scrambled = dict(document, manoeuvres=list(reversed(document["manoeuvres"])))
    assert plan.legs_of(scrambled) == plan.legs_of(document), "the order it is written changed it"


def test_a_plan_that_cannot_be_flown_says_so_in_sentences():
    wrong = plan.what_is_wrong({"manoeuvres": [
        {"id": "m1", "kind": "goto", "at": {"x": 1, "y": 2}, "next": "m4"},
        {"id": "m1", "kind": "spiral-descent", "at": {"x": 1, "y": 2}},
    ]})
    assert any("two manoeuvres are called m1" in one for one in wrong), wrong
    assert any("spiral-descent" in one and "cannot fly" in one for one in wrong), wrong
    assert any("m4" in one and "not in this plan" in one for one in wrong), wrong
    assert plan.what_is_wrong({"manoeuvres": []}) == ["the plan has no manoeuvres"]
    assert not plan.what_is_wrong(plan.plan_for(A_SURVEY, camera_half_angle=0.41))


# ── flying one ───────────────────────────────────────────────────────────────

def test_a_dive_can_be_flown_from_a_plan_it_is_given():
    """The whole of item 35, as one dive.

    The objective is there to be scored against; the plan is what is flown, and
    it is deliberately not the plan the platform would have made — a dogleg out
    to starboard on the way — so that flying it proves the document was used
    rather than quietly regenerated.
    """
    given = {
        "describedBy": plan.DESCRIBED_BY, "plan": "by hand, the long way round",
        "by": "a person", "start": "out",
        "manoeuvres": [
            {"id": "out", "kind": "goto", "at": {"x": 25.0, "y": 18.0, "depthM": 7.0},
             "arriveM": 3.0, "next": "in"},
            {"id": "in", "kind": "goto", "at": {"x": 50.0, "y": 0.0, "depthM": 7.0},
             "arriveM": 3.0},
        ],
    }
    dive = a_dive({"objective": {"kind": "reach", "dx": 50.0, "dy": 0.0, "radiusM": 3.0,
                                 "timeLimitS": 600}, "plan": given})
    assert dive.document is given, "the dive did not take the plan it was handed"
    assert dive.planned_by == "a person"
    run(dive, 60.0)
    assert dive.position[1] > 4.0, ("it went straight to the point rather than flying the plan "
                                    f"— {dive.position[1]:.1f} m to starboard")
    run(dive, 240.0)
    assert dive.task.detail()["arrived"], "and it never got there"


def test_a_plan_that_is_wrong_is_refused_and_the_platform_plans_instead():
    dive = a_dive({"objective": {"kind": "reach", "dx": 40.0, "dy": 0.0, "radiusM": 3.0},
                   "plan": {"manoeuvres": [{"id": "m1", "kind": "teleport"}]}})
    run(dive, 2.0)
    refused = [d for kind, d in dive.said if kind == "plan_refused"]
    assert refused, "a plan naming a manoeuvre this vehicle cannot fly was accepted"
    assert dive.planned_by == "the platform's planner", "and nothing planned in its place"
    assert dive.document and dive.document["manoeuvres"], "so there was nothing to fly"


def test_the_plan_is_written_down_with_the_recording(tmp_path):
    from recording import Recorder

    dive = a_dive({"objective": {"kind": "reach", "dx": 40.0, "dy": 0.0, "radiusM": 3.0}})
    dive.recorder = Recorder(tmp_path / "run", frames_hz=1.0)
    run(dive, 3.0)
    manifest = dive.recorder.close(dive, None)
    kept = json.loads((tmp_path / "run" / "plan.json").read_text())
    assert kept["manoeuvres"], "the plan was not kept with the recording"
    assert manifest["plan"]["by"] == "the platform's planner"
    assert "plan.json" in manifest["files"]
    assert plan.legs_of(kept), "and what was kept cannot be flown again"
