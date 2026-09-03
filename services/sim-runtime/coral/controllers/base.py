"""What every controller is, whoever wrote it.

A controller is handed what the vehicle knows about itself and answers with
what it wants the vehicle to do. That is the whole interface, and it is the
same for a person at the keys, for the station-keeping the runtime provides,
and for somebody's own stack talking over ROS 2 — so that nothing a pilot can
do is something a program cannot, and nothing a program can do is hidden from
the person watching.

A controller also declares what can be changed about it while it runs: each
parameter with a range and a unit, so that a console can draw it and a hand can
move it without the controller having to know what a console is.

Frames and units are the vehicle's: body frame with x forward, y to starboard,
z up; wrench as surge, sway, heave, roll, pitch, yaw; metres, radians, seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Observation:
    """What the vehicle knows about itself this step."""

    t: float
    position: np.ndarray          # world, metres; z up, so depth is -z
    velocity: np.ndarray          # body twist: u v w p q r
    rotation: np.ndarray          # body to world, 3x3
    floor: float | None           # the seabed's height under the vehicle, world z
    on_the_bottom: bool

    @property
    def depth(self) -> float:
        return float(-self.position[2])

    @property
    def altitude(self) -> float | None:
        return None if self.floor is None else float(self.position[2] - self.floor)

    @property
    def heading(self) -> float:
        """Yaw, radians, from the body x axis projected on the horizon."""
        return float(np.arctan2(self.rotation[1, 0], self.rotation[0, 0]))


@dataclass
class Command:
    """What a controller wants: a wrench, or the thrusters directly.

    A wrench is what most controllers should ask for, because turning it into
    thruster commands is the vehicle's business. Thruster commands are for a
    stack that has already done that allocation itself and must not have it
    redone.
    """

    wrench: np.ndarray | None = None       # body frame, newtons and newton-metres
    thrusters: np.ndarray | None = None    # per thruster, in [-1, 1]

    @classmethod
    def nothing(cls) -> "Command":
        return cls(wrench=np.zeros(6))


@dataclass
class Parameter:
    """One thing a hand may move while the controller runs."""

    name: str
    value: float
    low: float
    high: float
    unit: str = ""
    says: str = ""

    def set(self, value: float) -> None:
        self.value = float(min(self.high, max(self.low, float(value))))

    def describe(self) -> dict:
        return {"name": self.name, "value": round(self.value, 4),
                "low": self.low, "high": self.high, "unit": self.unit, "says": self.says}


class Controller:
    """The interface. Subclasses fill in observe() and declare parameters."""

    name: str = "controller"
    kind: str = "builtin"          # builtin | manual | external
    says: str = ""

    def __init__(self) -> None:
        self.parameters: dict[str, Parameter] = {}

    def declare(self, name: str, value: float, low: float, high: float,
                unit: str = "", says: str = "") -> Parameter:
        parameter = Parameter(name, float(value), float(low), float(high), unit, says)
        self.parameters[name] = parameter
        return parameter

    def __getitem__(self, name: str) -> float:
        return self.parameters[name].value

    def tune(self, name: str, value: float) -> bool:
        """Move a parameter. False if there is no such parameter."""
        parameter = self.parameters.get(name)
        if parameter is None:
            return False
        parameter.set(value)
        return True

    def observe(self, seen: Observation) -> Command:
        raise NotImplementedError

    def engage(self, seen: Observation) -> None:
        """Told it now has the vehicle, and where the vehicle is."""

    def status(self) -> dict:
        """Anything a console should show about this controller's state."""
        return {}

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "says": self.says,
                "parameters": [p.describe() for p in self.parameters.values()],
                "status": self.status()}
