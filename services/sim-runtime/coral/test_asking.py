"""A controller that asks a model, and what happens when the answer is bad.

Every dive in this record was flown by the same arrangement of PID loops
following a route worked out by trigonometry. The benchmark wants two
controllers over the same hundred dives; until there is something else in the
water there is one contestant.

What is tested here is not the model — it is the arrangement around it, which
is the part that has to be right before anybody spends a token: the vehicle
keeps flying while a decision is outstanding, a bad answer is refused rather
than flown, and what the thinking cost is recorded beside the score.
"""

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from controllers.asking import AskingController, _document_in  # noqa: E402
from controllers.base import Observation  # noqa: E402

GOAL = {"kind": "go", "to": [100.0, 0.0, -8.0], "radiusM": 2.0}


def a_controller(envelope=None, **environment):
    import os
    for key in ("CORAL_CITY_MODEL_URL", "CORAL_CITY_MODEL", "CORAL_CITY_MODEL_KEY"):
        os.environ.pop(key, None)
    os.environ.update(environment)
    asking = AskingController(np.full(6, 50.0), np.full(6, 12.0), 1.5, 0.005,
                              envelope=envelope)
    asking.tasked(GOAL)
    return asking


def seen_at(x=0.0, y=0.0, z=-8.0, t=0.0):
    return Observation(t=t, position=np.array([x, y, z]), velocity=np.zeros(6),
                       rotation=np.eye(3), floor=z - 5.0, on_the_bottom=False)


def test_json_is_found_however_the_model_wrapped_it():
    """Models fence their JSON, apologise before it, and explain after it
    however firmly they are asked not to."""
    fenced = "here you go:\n```json\n{\"plan\":\"x\",\"manoeuvres\":[]}\n```\nhope that helps"
    assert _document_in(fenced) == {"plan": "x", "manoeuvres": []}
    assert _document_in('{"plan":"y","manoeuvres":[]}') == {"plan": "y", "manoeuvres": []}
    assert _document_in("sorry, I cannot do that") is None
    assert _document_in("") is None
    assert _document_in('{"broken": ') is None


def test_with_no_model_configured_it_says_so_and_flies_nothing():
    """The one result this benchmark must never produce is a controller that
    quietly falls back to the trigonometry and is scored as a model."""
    asking = a_controller()
    assert asking.think(seen_at()) is None
    assert asking.said_nothing_configured
    assert asking.said()["configured"] is False
    assert asking.accepted == 0


def test_a_plan_beyond_the_vehicle_is_refused_and_said_out_loud():
    asking = a_controller(envelope={"maxDepthM": 100.0},
                          CORAL_CITY_MODEL_URL="http://nowhere/chat/completions",
                          CORAL_CITY_MODEL="pretend")
    asking._call = lambda said: (json.dumps({
        "plan": "much too deep",
        "manoeuvres": [{"id": "m1", "kind": "goto",
                        "at": {"x": 10.0, "y": 0.0, "depthM": 900.0}}]}), {})
    assert asking._ask(GOAL, seen_at()) is None
    assert asking.failures == 1
    said = asking.said()
    assert said["couldNot"], "it should say what was wrong"
    assert any("100" in reason for reason in said["couldNot"])


def test_a_model_that_answers_with_prose_is_refused_not_flown():
    asking = a_controller(CORAL_CITY_MODEL_URL="http://nowhere/chat/completions",
                          CORAL_CITY_MODEL="pretend")
    asking._call = lambda said: ("I would head roughly north-east for a bit.", {})
    assert asking._ask(GOAL, seen_at()) is None
    assert "the model did not answer with a plan" in asking.said()["couldNot"]


def test_a_model_that_cannot_be_reached_leaves_the_last_plan_flying():
    """A model having a bad minute must not put the vehicle into the seabed."""
    asking = a_controller(CORAL_CITY_MODEL_URL="http://nowhere/chat/completions",
                          CORAL_CITY_MODEL="pretend")
    good = {"plan": "fine", "manoeuvres": [
        {"id": "m1", "kind": "goto", "at": {"x": 50.0, "y": 0.0, "depthM": 8.0}}]}
    asking._call = lambda said: (json.dumps(good), {"prompt_tokens": 10, "completion_tokens": 20})
    decided = asking._ask(GOAL, seen_at())
    assert decided is not None
    asking.on_thought(decided)
    flying = list(asking.follower.route)
    assert flying, "it should be flying the plan"

    def explode(said):
        raise OSError("connection reset")
    asking._call = explode
    assert asking._ask(GOAL, seen_at()) is None
    assert list(asking.follower.route) == flying, "the last good plan is still flying"
    assert asking.failures == 1


def test_what_the_thinking_cost_is_recorded_beside_the_score():
    """A controller that is five per cent better and a second a step slower is
    not obviously better, and the record should not make you guess."""
    asking = a_controller(CORAL_CITY_MODEL_URL="http://nowhere/chat/completions",
                          CORAL_CITY_MODEL="minimax-m3")
    good = {"plan": "fine", "manoeuvres": [
        {"id": "m1", "kind": "goto", "at": {"x": 50.0, "y": 0.0, "depthM": 8.0}}]}
    asking._call = lambda said: (json.dumps(good),
                                 {"prompt_tokens": 400, "completion_tokens": 120})
    asking.on_thought(asking._ask(GOAL, seen_at()))
    said = asking.said()
    assert said["model"] == "minimax-m3"
    assert said["asked"] == 1 and said["accepted"] == 1 and said["failed"] == 0
    assert said["tokensIn"] == 400 and said["tokensOut"] == 120
    assert said["secondsThinking"] >= 0.0
