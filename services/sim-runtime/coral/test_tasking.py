"""Asking for a dive in words, and getting one that can be flown.

The chain is what is being protected: a sentence becomes a goal, the goal
becomes a plan document, the document is checked like any other, and a dive
flies it. Every link is a thing that exists on its own — which is why this
layer could be small, and why it had to be last.

Run with plain pytest from services/sim-runtime/coral.
"""

from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tasking  # noqa: E402
from controllers import plan as planning  # noqa: E402
from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = HERE.parents[2] / "catalog/vehicles/bluerov2/dynamics.json"
AT = (100.0, -20.0, -7.0)


def read(said: str, at=AT, heading: float = 0.0) -> dict:
    return tasking.understand(said, at=at, heading=heading, camera_half_angle=0.41)


def kinds(understood: dict) -> list[str]:
    return [m["kind"] for m in understood["plan"]["manoeuvres"]]


# ── what it understands ──────────────────────────────────────────────────────

def test_a_survey_asked_for_in_words_becomes_a_path_to_follow():
    understood = read("survey a 60 by 30 metre area at 4 metres up")
    assert kinds(understood) == ["follow-path"]
    points = understood["plan"]["manoeuvres"][0]["points"]
    assert len(points) > 8, "a survey of that size is more than a few lanes"
    assert understood["plan"]["manoeuvres"][0]["altitudeM"] == 4.0
    assert "60 by 30" in understood["read"][0]


def test_two_things_joined_by_then_are_two_manoeuvres_in_order():
    understood = read("survey a 40 by 20 metre area north, then come home and surface")
    assert kinds(understood) == ["follow-path", "goto"]
    first, second = understood["plan"]["manoeuvres"]
    assert first["next"] == second["id"], "the plan does not say which comes first"
    assert second["at"]["depthM"] <= 1.0, "it was asked to surface and did not"


def test_which_way_is_taken_from_the_words():
    east = read("go 250 metres east")["plan"]["manoeuvres"][0]["at"]
    assert east["y"] > AT[1] + 200, "east is +y in this world and it did not go there"
    assert abs(east["x"] - AT[0]) < 1.0
    north = read("go 250 metres north")["plan"]["manoeuvres"][0]["at"]
    assert north["x"] > AT[0] + 200, "north is +x and it did not go there"


def test_holding_station_asks_for_a_station_and_not_a_journey():
    understood = read("hold station here for 3 minutes")
    assert kinds(understood) == ["station-keeping"]
    assert "3 minutes" in understood["read"][0]
    assert planning.legs_of(understood["plan"]) == [], "holding is not somewhere to go"


def test_what_it_did_not_understand_it_says_rather_than_invents():
    understood = read("make me a sandwich")
    assert understood["plan"] is None, "it invented a dive out of nonsense"
    assert understood["missed"] == ["make me a sandwich"]
    assert "cannot do" in understood.get("why", "") or understood.get("why")


def test_half_understood_is_reported_as_half_understood():
    understood = read("survey a 40 by 20 metre area, then teach the fish to sing")
    assert kinds(understood) == ["follow-path"], "it flew the part it understood"
    assert any("fish" in one for one in understood["missed"]), understood["missed"]


def test_a_plan_read_from_words_passes_the_same_checks_as_any_other():
    understood = read("survey a 60 by 30 metre area at 5 metres up, then come home and surface")
    assert planning.what_is_wrong(understood["plan"]) == []


# ── and it flies ─────────────────────────────────────────────────────────────

def test_a_dive_flies_what_was_asked_for_in_words():
    """The whole chain, in one test: words, plan, dive, water."""
    said = "go 60 metres east, then come home"
    understood = read(said, at=(0.0, 0.0, -7.0))
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 900.0, "initialState": {"positionM": [0.0, 0.0, -7.0]},
             "objective": {"kind": "reach", "dx": 0.0, "dy": 60.0, "radiusM": 3.0,
                           "timeLimitS": 900, "plan": understood["plan"]}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **said_: None)
    dive.floor = -12.0
    dive.begin_task(brief["objective"])
    assert dive.document is understood["plan"], "the dive did not fly what was asked for"

    for _ in range(int(300 / dive.dt)):
        dive.step()
    # It went east, which is what was asked, and not north, which was not.
    assert dive.position[1] > 40.0, f"it did not go east — {dive.position[1]:.1f} m"
    assert abs(dive.position[0]) < 15.0, f"it wandered north — {dive.position[0]:.1f} m"
    for _ in range(int(400 / dive.dt)):
        dive.step()
    home = math.hypot(dive.position[0], dive.position[1])
    assert home < 8.0, f"it never came home — {home:.1f} m out"
