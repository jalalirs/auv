"""Somebody's own stack, on the other side of the ROS 2 boundary.

The bridge already turns /cmd_vel and /thruster_cmd into thruster commands;
this wraps it in the same interface every other controller has, so the helm can
treat "a program is flying" exactly like "the hold is flying": as one controller
among several, with a name, a status and a moment it took over.

A stack has the vehicle while it is talking. A command older than the patience
here is a stack that has stopped, and a vehicle whose controller has stopped
should not coast on the last thing it said.
"""

from __future__ import annotations

import numpy as np

from .base import Command, Controller, Observation


class StackController(Controller):
    # The slot, not the controller. What is flying has a name of its own and
    # `deployed` carries it: two of somebody's controllers on one bench were
    # both called "stack", so neither the record nor a comparison could tell
    # them apart — which is the one thing a benchmark is for. The name comes
    # off the dive, because the platform knows what it deployed; the ROS node
    # the bridge discovered is the fallback, because a stack somebody started
    # by hand still names itself.
    name = "stack"
    kind = "external"
    says = "An autonomy stack, over ROS 2, admitted against the vehicle's topic contract."

    def __init__(self, bridge, deployed: str = "", slug: str = "") -> None:
        super().__init__()
        self.bridge = bridge
        self.deployed = str(deployed or "")
        self.slug = str(slug or "")
        self.declare("patienceS", 1.0, 0.1, 10.0, "s", "how long without a command before the stack is considered gone")
        self._seen = 0
        self._last_at = -1e9

    def heard(self, t: float) -> bool:
        """Whether the stack has commanded since the last look, and when."""
        seen = int(getattr(self.bridge, "commands_seen", 0))
        if seen > self._seen:
            self._seen = seen
            self._last_at = t
        return bool(getattr(self.bridge, "commanded", False))

    def talking(self, t: float) -> bool:
        self.heard(t)
        return (t - self._last_at) <= self["patienceS"]

    def observe(self, seen: Observation) -> Command:
        return Command(thrusters=np.asarray(self.bridge.commands(), dtype=float))

    # ── what the stack declares about itself ─────────────────────────────────

    def tune(self, name: str, value: float) -> bool:
        if name in self.parameters:
            return super().tune(name, value)
        # Not ours: the stack's own, declared over ROS 2 and moved there.
        setter = getattr(self.bridge, "set_parameter", None)
        return bool(setter(name, value)) if setter is not None else False

    def flying_as(self) -> str:
        """What to call what is flying. Never a guess: the name the platform
        deployed it under, then the node it named itself, then the slot."""
        return self.deployed or (self.bridge_node() or "") or self.name

    def bridge_node(self) -> str | None:
        return getattr(self.bridge, "stack_node", None)

    def describe(self) -> dict:
        told = super().describe()
        told["flyingAs"] = self.flying_as()
        if self.slug:
            told["slug"] = self.slug
        theirs = getattr(self.bridge, "parameters", None)
        if theirs is not None:
            told["parameters"] = told["parameters"] + list(theirs())
        return told

    def status(self) -> dict:
        return {"commandsReceived": self._seen,
                "node": getattr(self.bridge, "stack_node", None),
                "lastCommandAgoS": None if self._last_at < 0 else round(max(0.0, -self._last_at), 2)}
