"""A person at the controls.

What a hand asks for is a fraction of what the vehicle can do on each axis,
which is what keys and sticks produce; turning that into a wrench is here,
because only the vehicle knows what full ahead means in newtons.

Assisted by default: on the axes the hand is not touching, the hold's depth and
heading autopilots keep the vehicle level and pointed. Push ahead and it goes
ahead at the depth it was at; let go and it stops where it is. That is how an
ROV with an autopilot flies, and a first-time pilot should meet that vehicle
rather than one that sinks the moment they think about something else.
"""

from __future__ import annotations

import numpy as np

from .base import Command, Controller, Observation
from .hold import HoldController


class ManualController(Controller):
    name = "manual"
    kind = "manual"
    says = "Keys or a stick, as fractions of what the vehicle can do; depth and heading held on the axes you leave alone."

    def __init__(self, capability: np.ndarray, hold: HoldController) -> None:
        super().__init__()
        self.capability = capability
        self.hold = hold
        self.declare("gain", 1.0, 0.1, 1.0, "", "how much of the vehicle's authority a full key asks for")
        self.declare("turnGain", 0.7, 0.1, 1.0, "", "the same, for yaw")
        self.declare("assist", 1.0, 0.0, 1.0, "", "1 holds depth and heading on untouched axes; 0 is raw")
        self.declare("deadband", 0.02, 0.0, 0.3, "", "stick travel that counts as nothing")
        self.hands = np.zeros(6)
        self._assisted_depth = None
        self._assisted_heading = None

    def ask(self, fraction) -> None:
        """What the hands are holding: six fractions in [-1, 1]."""
        asked = np.clip(np.asarray(fraction, dtype=float), -1.0, 1.0)
        asked[np.abs(asked) < self["deadband"]] = 0.0
        self.hands = asked

    @property
    def active(self) -> bool:
        return bool(np.any(self.hands))

    def engage(self, seen: Observation) -> None:
        self._assisted_depth = seen.depth
        self._assisted_heading = seen.heading
        self.hold.pilots.reset()

    def observe(self, seen: Observation) -> Command:
        fraction = self.hands * np.array([self["gain"]] * 3 + [self["turnGain"]] * 3)
        wrench = np.clip(fraction, -1.0, 1.0) * self.capability
        if self["assist"] >= 0.5:
            # Heave untouched: hold the depth the hand last let it settle at.
            if self.hands[2] == 0.0 and self._assisted_depth is not None:
                wrench[2] = self.hold.pilots.hold_depth(seen, self._assisted_depth, self.hold.dt)
            else:
                self._assisted_depth = seen.depth
            # Yaw untouched: hold the heading.
            if self.hands[5] == 0.0 and self._assisted_heading is not None:
                wrench[5] = self.hold.pilots.hold_heading(seen, self._assisted_heading, self.hold.dt)
            else:
                self._assisted_heading = seen.heading
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    @property
    def assisted_depth(self) -> float | None:
        return None if self["assist"] < 0.5 else self._assisted_depth

    @property
    def assisted_heading(self) -> float | None:
        return None if self["assist"] < 0.5 else self._assisted_heading

    def status(self) -> dict:
        return {"hands": [round(float(v), 2) for v in self.hands],
                "assistedDepthM": None if self._assisted_depth is None else round(self._assisted_depth, 2)}
