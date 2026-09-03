"""What a controller is.

The interface is the runtime's own — the same Observation, the same Command,
the same declared parameters — so a controller written here is not an
approximation of one that runs on the platform; it is one. The differences are
in what fills the observation: on a dive, sensors; in the tank, the physics or
the same sensor path, as you choose.

Frames and units are the vehicle's: body frame with x forward, y to starboard,
z up; a wrench is surge, sway, heave, roll, pitch, yaw; metres, radians,
seconds, newtons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Observation:
    """What the vehicle knows about itself this step."""

    t: float
    position: np.ndarray            # world, metres; z up, so depth is -z
    velocity: np.ndarray            # body twist: u v w p q r
    rotation: np.ndarray            # body to world, 3x3
    floor: float | None = None      # the seabed's height under the vehicle, world z
    on_the_bottom: bool = False
    # Whether position came from a navigation estimate — dead reckoning on a
    # DVL and an attitude — rather than being known. On a vehicle it always is.
    estimated: bool = True

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

    @property
    def pitch(self) -> float:
        return float(-np.arcsin(max(-1.0, min(1.0, float(self.rotation[2, 0])))))

    @property
    def roll(self) -> float:
        return float(np.arctan2(self.rotation[2, 1], self.rotation[2, 2]))


@dataclass
class Command:
    """What a controller wants: a wrench, or the thrusters directly.

    A wrench is what most controllers should ask for, because turning it into
    thruster commands is the vehicle's business. Thruster commands are for a
    controller that has already done that allocation itself.
    """

    wrench: np.ndarray | None = None       # body frame, newtons and newton-metres
    thrusters: np.ndarray | None = None    # per thruster, in [-1, 1]

    @classmethod
    def nothing(cls) -> "Command":
        return cls(wrench=np.zeros(6))

    @classmethod
    def wrench_of(cls, surge: float = 0.0, sway: float = 0.0, heave: float = 0.0,
                  roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0) -> "Command":
        return cls(wrench=np.array([surge, sway, heave, roll, pitch, yaw], dtype=float))

    @classmethod
    def thrusters_of(cls, *commands: float) -> "Command":
        return cls(thrusters=np.clip(np.array(commands, dtype=float), -1.0, 1.0))


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
    """Subclass this. Say which vehicle it is for, fill in observe(), and
    declare what may be moved."""

    name: str = "controller"
    says: str = ""
    # Which vehicle this controller is written for, by its catalogue slug.
    # Checked against the vehicle's description before the controller is
    # deployed, so that one asking for a sensor the vehicle lacks is refused
    # here rather than left waiting on a dive for a message that never comes.
    vehicle: str = "bluerov2"
    # What it commands with: "wrench" (allocated by the vehicle) or "thrusters".
    commands: str = "wrench"
    # Sensor kinds it cannot do without, beyond depth, attitude and rates.
    needs: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.parameters: dict[str, Parameter] = {}
        from . import vehicles
        self.described = vehicles.load(self.vehicle)

    def declare(self, name: str, value: float, low: float, high: float,
                unit: str = "", says: str = "") -> Parameter:
        parameter = Parameter(name, float(value), float(low), float(high), unit, says)
        self.parameters[name] = parameter
        return parameter

    def __getitem__(self, name: str) -> float:
        return self.parameters[name].value

    def tune(self, name: str, value: float) -> bool:
        parameter = self.parameters.get(name)
        if parameter is None:
            return False
        parameter.set(value)
        return True

    # ── what a subclass fills in ─────────────────────────────────────────────

    def engage(self, seen: Observation) -> None:
        """Told it now has the vehicle, and where the vehicle is."""

    def observe(self, seen: Observation) -> Command:
        raise NotImplementedError

    def status(self) -> dict:
        return {}

    def describe(self) -> dict:
        return {"name": self.name, "kind": "external", "says": self.says,
                "vehicle": self.vehicle, "commands": self.commands,
                "parameters": [p.describe() for p in self.parameters.values()],
                "status": self.status()}
