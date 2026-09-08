"""A controller that thinks before it acts, and flies while it thinks.

This is the shape a model-driven controller has, with the model left out. It
is handed the goal rather than a route, works out for itself how to satisfy it,
and does that working out on the slow loop — where taking a second or two is
allowed, because that is what asking anything worth asking costs.

Everything about it that matters is the arrangement, not the thinking:

  * the flight loop follows whatever plan it currently holds, every step,
    without ever waiting for a decision;
  * the slow loop is where the decision happens, and may take as long as it
    takes — swap `_decide` for a call to a vision-language model and nothing
    else here changes;
  * a plan that arrives is picked up between steps, so there are no locks;
  * a decision that fails leaves the last one in place and the vehicle flying.

What it decides is deliberately modest: the same route the platform's planner
would work out, re-planned from where the vehicle currently believes it is —
which, unlike a route laid down once at the start, quietly corrects for a leg
that was flown badly. The interesting part is that it is decided at all, on a
clock slow enough for something real to be doing the deciding.
"""

from __future__ import annotations

import time

import numpy as np

from . import plan
from .base import Command, Controller, Observation
from .pursue import PursueController


class PonderController(Controller):
    """Plans on the slow loop; follows that plan on the fast one."""

    name = "ponder"
    kind = "builtin"
    says = "Works out its own way of doing the task, and keeps flying while it does."
    thinks_every = 20.0

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float,
                 camera_half_angle: float | None = None) -> None:
        super().__init__()
        # The follower is the ordinary one. What makes this a different
        # controller is where its route comes from, not how it is flown.
        self.follower = PursueController(capability, mass, trim_n, dt)
        self.camera_half_angle = camera_half_angle
        self.plans = 0
        self.declare("thinkS", 0.0, 0.0, 10.0, "s",
                     "How long a decision takes. Stands in for a model call.")
        self.declare("everyS", self.thinks_every, 5.0, 300.0, "s",
                     "Simulated seconds between decisions.")

    # ── the fast loop ────────────────────────────────────────────────────────

    def observe(self, seen: Observation) -> Command:
        return self.follower.observe(seen)

    def engage(self, seen: Observation) -> None:
        self.follower.engage(seen)

    # ── the slow loop ────────────────────────────────────────────────────────

    def think(self, seen: Observation):
        """Work out a route to the goal. Slowly, off the flight loop."""
        self.thinks_every = self["everyS"]
        goal = dict(self.goal or {})
        if not goal:
            return None
        return self._decide(goal, np.asarray(seen.position, dtype=float))

    def _decide(self, goal: dict, believed: np.ndarray):
        """The part a model would replace.

        Given what the dive is for and where the vehicle believes it is, answer
        with a route. `thinkS` is here so that a slow decision can be tried on
        purpose: the platform must fly correctly while one is outstanding, and
        that is not something to find out for the first time with a model on
        the other end.
        """
        pause = self["thinkS"]
        if pause > 0:
            time.sleep(pause)
        return plan.route_for(goal, believed=believed,
                              camera_half_angle=self.camera_half_angle)

    def on_thought(self, decided) -> None:
        """A route came back. Fly it."""
        if not decided:
            return
        self.plans += 1
        self.follower.steer(decided)

    # ── what a console is shown ──────────────────────────────────────────────

    def status(self) -> dict:
        return {"plans": self.plans, "goal": (self.goal or {}).get("kind"),
                **self.follower.status()}
