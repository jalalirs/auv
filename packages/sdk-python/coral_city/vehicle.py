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
        """Which command kinds this vehicle takes.

        Three, not two. A hull with no thrusters takes neither a wrench nor
        thruster commands — it takes its own actuators, by their own names,
        and a check that only knew the first two told the author of a glider
        controller that their vehicle accepted nothing.
        """
        names = {t.name for t in self.subscribes}
        kinds = []
        if "/cmd_vel" in names:
            kinds.append("wrench")
        if "/thruster_cmd" in names:
            kinds.append("thrusters")
        if self.actuators:
            kinds.append("actuators")
        return tuple(kinds)

    @property
    def actuators(self) -> tuple[str, ...]:
        """What this vehicle can be asked for by name, if anything.

        A buoyancy glider's pump and its sliding mass. What a package declares
        is the *limits* — how far the pump goes and how fast — and what a
        controller sends is the demand, so the two are named differently and
        this maps between them. A controller author should not have to read
        the runtime to find that out.
        """
        said = (self.dynamics or {}).get("actuators") or {}
        if not isinstance(said, dict):
            return ()
        asks = []
        if "vbdCcRange" in said:
            asks.append("vbdCc")
        if float(said.get("massShiftM", 0.0) or 0.0) > 0.0:
            asks.append("pitchM")
        if float(said.get("massRollM", said.get("massShiftM", 0.0)) or 0.0) > 0.0:
            asks.append("rollM")
        return tuple(asks)

    def limits_of(self, actuator: str):
        """How far one actuator goes, in the vehicle's own units."""
        said = (self.dynamics or {}).get("actuators") or {}
        if actuator == "vbdCc":
            low, high = said.get("vbdCcRange", [0.0, 0.0])
            return (float(low), float(high))
        if actuator == "pitchM":
            reach = float(said.get("massShiftM", 0.0) or 0.0)
            return (-reach, reach)
        if actuator == "rollM":
            reach = float(said.get("massRollM", said.get("massShiftM", 0.0)) or 0.0)
            return (-reach, reach)
        return (0.0, 0.0)

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
        if commands not in ("wrench", "thrusters", "actuators"):
            problems.append(
                f"commands must be 'wrench', 'thrusters' or 'actuators', not '{commands}'")
        elif commands not in self.accepts:
            problems.append(f"commands with a {commands}, which this vehicle does not accept "
                            f"(it takes {', '.join(self.accepts) or 'nothing'})")
        for kind in getattr(controller_class, "needs", ()):
            if kind not in self.carries:
                problems.append(f"needs a {kind}, which this vehicle does not carry "
                                f"(it has {', '.join(self.carries)})")
        return problems
