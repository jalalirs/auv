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

from dataclasses import dataclass

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
    stack that has already done that allocation itself and must not have it
    redone.
    """

    wrench: np.ndarray | None = None       # body frame, newtons and newton-metres
    thrusters: np.ndarray | None = None    # per thruster, in [-1, 1]
    # What a vehicle that is not moved by thrust is asked for, in its own
    # terms. A buoyancy glider has no propeller anywhere on it: it is told how
    # much water to displace and where to put its mass, and its wings turn
    # falling into going somewhere. There is no wrench to ask for and no
    # thruster to command, and a platform whose only two answers are those has
    # quietly decided what kind of vehicle a vehicle is.
    #
    # Deliberately a plain mapping. What the actuators are belongs to the
    # vehicle's package, not to this file, and a helm that had to know the
    # names would be the same assumption in a different place.
    actuators: dict | None = None

    @classmethod
    def nothing(cls) -> "Command":
        return cls(wrench=np.zeros(6))

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


class Controller:
    """The interface. Subclasses fill in observe() and declare parameters.

    Two clocks, and a controller may use one or both. `observe` is the flight
    loop: it is called every physics step, must return quickly, and must not
    wait for anything. `think` is the slow one: it is called on its own thread,
    no faster than `thinks_every` simulated seconds, may take as long as it
    needs, may reach the network, may call a model, and may fail — and while it
    is away the vehicle keeps flying on whatever it last decided.

    That split is what makes a controller that reasons possible at all. A
    model asked to look at a frame answers in a second or two; put that in the
    flight loop and the vehicle stops sixty times a second.
    """

    name: str = "controller"
    kind: str = "builtin"          # builtin | manual | external
    says: str = ""
    # How often this controller wants to think, in simulated seconds. None
    # means it does not — most controllers are arithmetic and want the fast
    # loop only.
    thinks_every: float | None = None

    def __init__(self) -> None:
        self.parameters: dict[str, Parameter] = {}
        self.goal: dict = {}

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

    def think(self, seen: Observation):
        """Decide something, slowly, off the flight loop.

        Called on its own thread when `thinks_every` says so. Whatever it
        returns is handed to `on_thought` on the flight thread, so neither of
        these ever needs a lock. Raising is allowed: it is counted, reported,
        and the vehicle carries on with the last thought that worked.
        """
        return None

    def on_thought(self, decided) -> None:
        """Take delivery of what `think` decided. On the flight thread."""

    def tasked(self, goal: dict) -> None:
        """Told what the dive is for, in the world's own coordinates.

        A controller that plans for itself needs the goal rather than a route
        — that is the whole of the difference between being driven and being
        asked. Stored by default; ignored by controllers that are handed a
        route instead.
        """
        self.goal = dict(goal or {})

    def engage(self, seen: Observation) -> None:
        """Told it now has the vehicle, and where the vehicle is."""

    def delivered(self, asked: np.ndarray, given: np.ndarray) -> None:
        """Told what the vehicle actually did with the wrench it asked for.

        Between a controller and the thrusters sit the attitude guard and the
        bottom guard, and both of them take force away. A controller never saw
        that happen: it asked for twenty newtons, was given seven, and the only
        evidence was that the error would not close. An integrator in that
        position winds up against a ceiling it has not been told about, and
        every newton-second it accumulates is discarded — so it cannot even
        wind down again once the vehicle is free.

        This is the other half of the conversation. The default is to ignore
        it, because a controller that allocates its own thrusters was never
        guarded in the first place.
        """

    def status(self) -> dict:
        """Anything a console should show about this controller's state."""
        return {}

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "says": self.says,
                "parameters": [p.describe() for p in self.parameters.values()],
                "status": self.status()}
