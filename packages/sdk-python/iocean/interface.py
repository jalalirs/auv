"""The interface between a controller and a vehicle. One file, both sides.

A controller is handed what the vehicle knows about itself and answers with
what it wants the vehicle to do. That is the whole of it, and it is the same
for a person at the keys, for the station-keeping the runtime provides, and
for somebody's own stack in a container talking ROS 2 — so that nothing a
pilot can do is something a program cannot, and nothing a program can do is
hidden from the person watching.

**Why this file exists.** It was two files. `Observation` and `Command` were
declared once in the runtime and once in this SDK, and the SDK's docstring
promised "the interface is the runtime's own". They had already drifted: the
runtime's observation carries the sonar's nearest return and its whole fan,
and the SDK's did not — so a customer writing against the published interface
could not see the one thing a controller learns that nobody told it, which is
that there is something in the water. Meanwhile the SDK's observation said
whether the position was an estimate and the runtime's did not.

Two implementations of one idea agree until they do not, and the disagreement
looks like a finding. Here it would have been a customer finding it.

The interface lives in the published package rather than inside the runtime
because the published package is the promise. The runtime imports it and is
therefore bound by it; the image carries a copy of this file, placed there by
the build.

Frames and units are the vehicle's: body frame with x forward, y to starboard,
z up; a wrench is surge, sway, heave, roll, pitch, yaw; metres, radians,
seconds, newtons.
"""

from __future__ import annotations

from dataclasses import dataclass

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

    # What the sonar last saw, when the vehicle carries one and something came
    # back. `{"rangeM":, "bearingRad":, "beam":}` for the nearest return, where
    # the bearing is off the nose and positive to starboard — so turning away
    # from it is a sign.
    #
    # This is the one thing a controller learns that nobody told it. Everything
    # else it is handed comes from the dive: where it is, what it is for, what
    # the plan was. A thing in the water that is not in the plan is only ever
    # going to arrive this way.
    seen: dict | None = None

    # The whole fan: `{"bearingsRad": [...], "rangesM": [...]}`, where a range
    # is NaN for a beam that came back with nothing. The nearest return above
    # is the convenience; this is the instrument.
    #
    # A controller steering on the nearest return alone cannot avoid anything
    # dead ahead: the closest beam flips between the two either side of centre
    # as the noise moves, the vehicle is told to turn first one way and then
    # the other, and it drives straight into the thing while chattering. What
    # it needs is where the *gap* is, which is a question about the fan.
    sonar: dict | None = None

    # Whether the position above is a navigation estimate — dead reckoning on
    # a Doppler log and an attitude — rather than known. On a real vehicle it
    # always is. In a simulator it is whichever the dive was set up with, and
    # a controller that is scored against the truth while steering on the
    # estimate should be able to tell which one it is holding.
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
    """What a controller wants: a wrench, the thrusters, or the actuators.

    A wrench is what most controllers should ask for, because turning it into
    thruster commands is the vehicle's business. Thruster commands are for a
    controller that has already done that allocation itself and must not have
    it redone.

    And `actuators` is for a vehicle that is not moved by thrust at all. A
    buoyancy glider has no propeller anywhere on it: it is told how much water
    to displace and where to put its mass, and its wings turn falling into
    going somewhere. There is no wrench to ask for and no thruster to command,
    and a platform whose only two answers are those has quietly decided what
    kind of vehicle a vehicle is.

    Deliberately a plain mapping. What the actuators are belongs to the
    vehicle's package and not to this file; a controller that had to be
    updated here every time somebody published a hull with a different pump
    would be the same assumption in a different place.
    """

    wrench: np.ndarray | None = None       # body frame, newtons and newton-metres
    thrusters: np.ndarray | None = None    # per thruster, in [-1, 1]
    actuators: dict | None = None          # by name, in the vehicle's own terms

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

    @classmethod
    def actuators_of(cls, **asked: float) -> "Command":
        """Ask a vehicle for its own actuators, by their own names.

            Command.actuators_of(buoyancyCm3=180.0, massAtM=0.012)

        The names are the vehicle package's, so `coral-city vehicles` is how
        you find out what a hull will answer to.
        """
        return cls(actuators={name: float(value) for name, value in asked.items()})

    def is_empty(self) -> bool:
        return self.wrench is None and self.thrusters is None and self.actuators is None


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
