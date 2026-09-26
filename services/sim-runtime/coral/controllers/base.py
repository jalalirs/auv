"""What every controller is, whoever wrote it.

A controller is handed what the vehicle knows about itself and answers with
what it wants the vehicle to do. That is the whole interface, and it is the
same for a person at the keys, for the station-keeping the runtime provides,
and for somebody's own stack talking over ROS 2 — so that nothing a pilot can
do is something a program cannot, and nothing a program can do is hidden from
the person watching.

`Observation`, `Command` and `Parameter` are not declared here. They are
declared once, in the published SDK, and imported by this file — because the
SDK is what a customer was given and the runtime is what has to honour it.
They used to be declared in both places, and they had already drifted: the
observation a customer could see had no sonar on it, which is the one thing a
controller learns that nobody told it.

A controller also declares what can be changed about it while it runs: each
parameter with a range and a unit, so that a console can draw it and a hand can
move it without the controller having to know what a console is.

Frames and units are the vehicle's: body frame with x forward, y to starboard,
z up; wrench as surge, sway, heave, roll, pitch, yaw; metres, radians, seconds.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

try:
    from coral_city.interface import Command, Observation, Parameter
except ImportError:
    # Run from the repository rather than from the image, where the build
    # puts the SDK on the path. Not a fallback copy — the same file, found a
    # different way. If it is not there either, this raises, because a
    # runtime that quietly invented its own interface is the fault this file
    # exists to prevent.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]
                           / "packages" / "sdk-python"))
    from coral_city.interface import Command, Observation, Parameter

__all__ = ["Command", "Controller", "Observation", "Parameter"]


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
