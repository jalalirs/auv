"""A controller that asks a model what to do, while the vehicle keeps flying.

Every dive in this record was flown by the same arrangement of PID loops
following a route worked out by two hundred lines of trigonometry. That is the
right baseline and it is only a baseline: the benchmark in item 37 wants two
controllers over the same hundred dives, and until there is something else to
put in the water there is one contestant.

This is the something else. It is `ponder` with the model put in: handed the
goal rather than a route, told where the vehicle believes it is and how the
task is going, and asked for a plan document — the same artefact a person would
write and the platform's own planner emits, so what comes back is comparable
with what the loops would have done rather than a different kind of thing.

The arrangement around it is what makes it usable on a vehicle:

  * the flight loop never waits. A decision is outstanding for as long as it
    takes and the vehicle flies the last plan meanwhile, which is what a real
    one does and the only honest way to charge for thinking;
  * thinking is charged in *simulated* seconds by the machinery in
    `thinking.py`, so a controller that scores well by pausing the world does
    not get away with it;
  * a plan that comes back wrong — malformed, empty, or asking for more than
    the vehicle has — is refused and the last good one keeps flying. A model
    that has a bad minute does not put the vehicle into the seabed;
  * what it cost is recorded. Tokens and latency go into the result beside the
    score, because a controller that is five per cent better and a second a
    step slower is not obviously better.

With no model configured it says so and flies nothing, rather than quietly
falling back to the planner and being scored as if a model had done it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import numpy as np

from . import plan
from .base import Command, Controller, Observation
from .pursue import PursueController

ASKED_FOR = """You are the autonomy on an underwater vehicle. You are given \
what the dive is for and what the vehicle currently believes about itself, and \
you answer with a plan.

Answer with JSON only, no prose and no code fence, shaped like this:

{"plan": "a short name",
 "manoeuvres": [
   {"id": "m1", "kind": "goto", "at": {"x": 120.0, "y": -30.0, "altitudeM": 3.0},
    "arriveM": 2.0, "speedMs": 0.4, "next": "m2"},
   {"id": "m2", "kind": "follow-path",
    "points": [{"x": 120.0, "y": -30.0}, {"x": 180.0, "y": -30.0}],
    "altitudeM": 3.0}
 ]}

Kinds are "goto", "follow-path" and "station-keeping". Coordinates are metres \
in the site's own frame, the same frame the goal is stated in. `altitudeM` is \
height above the seabed; `depthM` is depth below the surface; give one, not \
both. Every manoeuvre needs an id, and `next` chains them.

Say only what you want done. Do not explain."""


class AskingController(Controller):
    """Plans by asking a model; flies the answer with the ordinary follower."""

    name = "asking"
    kind = "builtin"
    says = "Asks a model for a plan, and keeps flying the last one while it waits."
    thinks_every = 60.0

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float,
                 camera_half_angle: float | None = None, envelope: dict | None = None) -> None:
        super().__init__()
        self.follower = PursueController(capability, mass, trim_n, dt)
        self.camera_half_angle = camera_half_angle
        self.envelope = dict(envelope or {})
        self.declare("everyS", self.thinks_every, 10.0, 900.0, "s",
                     "Simulated seconds between decisions.")
        self.declare("temperature", 0.2, 0.0, 2.0, "",
                     "How much the model is allowed to vary its answer.")

        self.url = os.environ.get("CORAL_CITY_MODEL_URL", "")
        self.model = os.environ.get("CORAL_CITY_MODEL", "")
        self.key = os.environ.get("CORAL_CITY_MODEL_KEY", "")
        self.max_tokens = int(os.environ.get("CORAL_CITY_MODEL_MAX_TOKENS", "4000"))

        # What it cost and how often it was wrong. Beside the score, because a
        # controller that thinks for a second a step is a different proposition
        # from one that does not, whatever it scores.
        self.asked = 0
        self.accepted = 0
        self.refused: list[str] = []
        self.failures = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.seconds_thinking = 0.0
        self.last_plan: dict | None = None
        self.said_nothing_configured = False

    # ── the fast loop ────────────────────────────────────────────────────────

    def observe(self, seen: Observation) -> Command:
        return self.follower.observe(seen)

    def engage(self, seen: Observation) -> None:
        self.follower.engage(seen)

    def delivered(self, asked, given) -> None:
        self.follower.delivered(asked, given)

    def limit(self, authority: np.ndarray) -> None:
        self.follower.limit(authority)

    # ── the slow loop ────────────────────────────────────────────────────────

    def think(self, seen: Observation):
        self.thinks_every = self["everyS"]
        goal = dict(self.goal or {})
        if not goal:
            return None
        if not (self.url and self.model):
            # Silence rather than the planner. A controller that quietly falls
            # back to the trigonometry and is scored as a model is the one
            # result this benchmark must never produce.
            self.said_nothing_configured = True
            return None
        return self._ask(goal, seen)

    def _ask(self, goal: dict, seen: Observation):
        believed = np.asarray(seen.position, dtype=float)
        asking = {
            "goal": goal,
            "vehicle": {
                "believedPosition": [round(float(v), 2) for v in believed],
                "depthM": round(seen.depth, 2),
                "altitudeM": None if seen.altitude is None else round(seen.altitude, 2),
                "headingDeg": round(float(np.degrees(seen.heading)), 1),
                "envelope": self.envelope,
            },
            "elapsedS": round(float(seen.t), 1),
        }
        began = time.monotonic()
        self.asked += 1
        try:
            answer, usage = self._call(json.dumps(asking))
        except Exception as trouble:
            self.failures += 1
            self.refused.append(f"the model could not be reached: {str(trouble)[:120]}")
            return None
        finally:
            self.seconds_thinking += time.monotonic() - began
        self.tokens_in += int(usage.get("prompt_tokens", 0) or 0)
        self.tokens_out += int(usage.get("completion_tokens", 0) or 0)

        document = _document_in(answer)
        if document is None:
            self.failures += 1
            self.refused.append("the model did not answer with a plan")
            return None
        document.setdefault("describedBy", plan.DESCRIBED_BY)
        document.setdefault("for", goal)
        document.setdefault("start", (document.get("manoeuvres") or [{}])[0].get("id"))
        wrong = plan.what_is_wrong(document, self.envelope or None)
        if wrong:
            # Refused, and said so. The last good plan keeps flying, which is
            # the whole reason the two loops are separate.
            self.failures += 1
            self.refused.extend(wrong[:4])
            return None
        return document

    def _call(self, said: str) -> tuple[str, dict]:
        """One request, in whichever shape the endpoint speaks."""
        completions = "/chat/completions" in self.url or self.url.endswith("/completions")
        headers = {"content-type": "application/json"}
        if self.key:
            headers["authorization"] = f"Bearer {self.key}"
        if completions:
            body = {"model": self.model, "max_tokens": self.max_tokens,
                    "temperature": float(self["temperature"]),
                    "messages": [{"role": "system", "content": ASKED_FOR},
                                 {"role": "user", "content": said}]}
        else:
            body = {"model": self.model, "max_tokens": self.max_tokens,
                    "system": ASKED_FOR,
                    "messages": [{"role": "user", "content": said}]}
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=240) as answer:
            got = json.loads(answer.read().decode())
        usage = got.get("usage") or {}
        if completions:
            text = (got.get("choices") or [{}])[0].get("message", {}).get("content", "")
        else:
            text = "".join(part.get("text", "") for part in got.get("content", [])
                           if part.get("type") == "text")
            usage = {"prompt_tokens": usage.get("input_tokens"),
                     "completion_tokens": usage.get("output_tokens")}
        return text or "", usage

    def on_thought(self, decided) -> None:
        if not decided:
            return
        self.accepted += 1
        self.last_plan = decided
        self.follower.steer(plan.legs_of(decided))

    # ── what a console and a record are told ─────────────────────────────────

    def said(self) -> dict:
        """What the thinking cost, for the result."""
        return {
            "model": self.model or None,
            "asked": self.asked, "accepted": self.accepted, "failed": self.failures,
            "tokensIn": self.tokens_in, "tokensOut": self.tokens_out,
            "secondsThinking": round(self.seconds_thinking, 2),
            # What it could not do, in its own words where they were its own.
            # A dive that scored badly because every plan was refused is a
            # different result from one that scored badly because the plans
            # were bad, and the difference should not have to be inferred.
            "couldNot": self.refused[:8],
            "configured": bool(self.url and self.model),
        }

    def status(self) -> dict:
        return {"plans": self.accepted, "asked": self.asked,
                "goal": (self.goal or {}).get("kind"),
                **self.follower.status()}


def _document_in(text: str) -> dict | None:
    """The plan in whatever the model wrapped it in.

    Models fence their JSON, apologise before it, and explain after it however
    firmly they are asked not to. Taking the outermost braces is not elegant
    and it is what makes the difference between a controller that works and
    one that works when the model is in a good mood.
    """
    if not text:
        return None
    body = text.strip()
    if body.startswith("```"):
        body = body.split("```")[1] if "```" in body[3:] else body[3:]
        if body.startswith("json"):
            body = body[4:]
    opened, closed = body.find("{"), body.rfind("}")
    if opened < 0 or closed <= opened:
        return None
    try:
        document = json.loads(body[opened:closed + 1])
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None
