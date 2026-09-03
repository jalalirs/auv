"""A vehicle, as the catalogue describes it.

Generated from the catalogue rather than typed, so that what a controller is
checked against is what the platform will actually give it: the thrusters and
their layout, the sensors it carries, the topics it publishes and acts on, and
how much force it can produce on each axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Thruster:
    name: str
    position: tuple[float, float, float]
    direction: tuple[float, float, float]


@dataclass(frozen=True)
class Sensor:
    kind: str
    name: str


@dataclass(frozen=True)
class Topic:
    name: str
    type: str
    note: str = ""


@dataclass(frozen=True)
class Vehicle:
    slug: str
    name: str
    mass_kg: float
    net_buoyancy_n: float           # positive floats
    thrusters: tuple[Thruster, ...]
    sensors: tuple[Sensor, ...]
    publishes: tuple[Topic, ...]    # what the vehicle sends
    subscribes: tuple[Topic, ...]   # what it acts on
    capability: tuple[float, float, float, float, float, float]   # most force per axis
    dynamics: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def accepts(self) -> tuple[str, ...]:
        """Which command kinds this vehicle takes: wrench, thrusters, or both."""
        names = {t.name for t in self.subscribes}
        kinds = []
        if "/cmd_vel" in names:
            kinds.append("wrench")
        if "/thruster_cmd" in names:
            kinds.append("thrusters")
        return tuple(kinds)

    @property
    def carries(self) -> tuple[str, ...]:
        return tuple(sorted({s.kind for s in self.sensors}))

    @property
    def most(self) -> np.ndarray:
        return np.array(self.capability, dtype=float)

    def check(self, controller_class) -> list[str]:
        """Why this controller could not fly this vehicle. Empty is fine."""
        problems: list[str] = []
        if getattr(controller_class, "vehicle", None) != self.slug:
            problems.append(f"written for '{getattr(controller_class, 'vehicle', None)}', not '{self.slug}'")
        commands = getattr(controller_class, "commands", "wrench")
        if commands not in ("wrench", "thrusters"):
            problems.append(f"commands must be 'wrench' or 'thrusters', not '{commands}'")
        elif commands not in self.accepts:
            problems.append(f"commands with a {commands}, which this vehicle does not accept "
                            f"(it takes {', '.join(self.accepts) or 'nothing'})")
        for kind in getattr(controller_class, "needs", ()):
            if kind not in self.carries:
                problems.append(f"needs a {kind}, which this vehicle does not carry "
                                f"(it has {', '.join(self.carries)})")
        return problems
