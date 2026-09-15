"""The platform's planner, with its eyes open.

`pursue` flies the route it was given and nothing else. That is right for what
it is — the floor a written controller has to beat — and it means it will drive
straight into anything the route does not know about, because a route is a list
of points and a point is not a warning.

This is the same controller with the sonar switched on. It still flies the
route; it just declines to fly through things. The difference between the two
on one dive is the whole argument for having a sonar at all, and it is the one
comparison a reef programme can make without writing a line of code.

**What it does.** A return close ahead is something in the way. It looks across
the whole fan for the widest run of beams with nothing in them, steers at the
middle of that gap, and eases off the throttle — both harder the closer the
thing is. When the way is clear again the route pulls it back on.

Steering at the gap rather than away from the nearest return is not a
refinement; it is the difference between working and not. A thing dead ahead is
symmetric, so the closest beam flips between the two either side of centre as
the noise moves: a controller told to turn away from *that* is told to go left,
then right, then left, and drives straight into the thing while chattering. It
did, on the first version of this file.

And it commits. Once it has picked a side it keeps it until the way is clear,
because a vehicle that reconsiders every fifth of a second is a vehicle that
never finishes a turn.

**What it does not do.** It does not remember. Every ping is judged on its own,
so a vehicle that has gone past something and turned back will meet it again
as a surprise. A controller that mapped what it saw would be a better
controller and a much longer file, and this one exists to make the sensor
worth having rather than to be the last word on using it.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Observation
from .hold import wrap
from .pursue import PursueController


class WaryController(PursueController):
    """Follow a route, and steer round what the sonar sees in it."""

    name = "wary"
    kind = "builtin"
    says = "Flies the route, and declines to fly through what the sonar sees."

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float) -> None:
        super().__init__(capability, mass, trim_n, dt)
        self.declare("standOffM", 6.0, 1.0, 30.0, "m",
                     "how close a return has to be before it is in the way")
        self.declare("aheadDeg", 50.0, 10.0, 90.0, "°",
                     "how far off the nose still counts as ahead")
        self.declare("leanDeg", 55.0, 5.0, 90.0, "°",
                     "how far it turns away at the closest it will get")
        self.declare("slowestShare", 0.25, 0.0, 1.0, "",
                     "how much of its speed it keeps when something is right there")
        self.declare("commitS", 4.0, 0.0, 30.0, "s",
                     "how long it keeps the way round it chose")
        self.avoided = 0
        self.closest = None
        # The way round it picked, and when. A vehicle that reconsiders every
        # fifth of a second never finishes a turn.
        self.going = None
        self.chose_at = None

    def in_the_way(self, seen: Observation):
        """What the sonar saw that is worth steering around, or nothing.

        Ahead and close. A return sixty degrees to starboard is a thing being
        passed, not a thing being driven at, and a controller that swerved for
        everything it could see would never fly a straight line anywhere near
        a reef.
        """
        said = getattr(seen, "seen", None)
        if not said:
            return None
        bearing = float(said.get("bearingRad", 0.0))
        if abs(bearing) > math.radians(float(self["aheadDeg"])):
            return None
        near = float(said.get("rangeM", 0.0))
        if near <= 0.0 or near > float(self["standOffM"]):
            return None
        return {"rangeM": near, "bearingRad": bearing,
                # Nought at the stand-off and one when it is right there.
                "urgency": max(0.0, min(1.0, 1.0 - near / max(1e-6, float(self["standOffM"]))))}

    def the_gap(self, seen: Observation, close: dict) -> float:
        """Which way to go: the middle of the widest clear run of beams.

        A beam with nothing in it, or nothing inside the stand-off, is a way
        through. The widest run of them is the gap, and its middle is where to
        point. If the whole fan is blocked there is no gap, and the answer is
        to turn away from the nearest return as hard as it goes — which is
        what is left when there is nowhere to go.
        """
        fan = getattr(seen, "sonar", None)
        if not fan:
            return -math.copysign(math.radians(float(self["leanDeg"])),
                                  close["bearingRad"] or 1.0)
        bearings = np.asarray(fan["bearingsRad"], dtype=float)
        ranges = np.asarray(fan["rangesM"], dtype=float)
        clear = ~np.isfinite(ranges) | (ranges > float(self["standOffM"]))
        best, run, start = (0, None), 0, 0
        for i, ok in enumerate(clear):
            if ok:
                if run == 0:
                    start = i
                run += 1
                if run > best[0]:
                    best = (run, (start, i))
            else:
                run = 0
        if best[1] is None:
            return -math.copysign(math.radians(float(self["leanDeg"])),
                                  close["bearingRad"] or 1.0)
        first, last = best[1]
        return float((bearings[first] + bearings[last]) / 2.0)

    def observe(self, seen: Observation) -> Command:
        close = self.in_the_way(seen)
        if close is None:
            self.closest = None
            self.going = None
            self.chose_at = None
            return super().observe(seen)

        self.avoided += 1
        self.closest = round(close["rangeM"], 2)
        # Picked once and kept, until the way is clear or the commitment runs
        # out. Reconsidering every ping is how a vehicle chatters into a thing.
        if self.going is None or (self.chose_at is not None
                                  and float(seen.t) - self.chose_at > float(self["commitS"])):
            self.going = self.the_gap(seen, close)
            self.chose_at = float(seen.t)

        # Fly the route as though the thing were not there, and keep its depth
        # — then go somewhere else. The *direction it travels* is what has to
        # change, not the direction it points: this is a vectored hull that
        # moves sideways as happily as forwards, so turning the nose while
        # still asking for the route's velocity crabs it into the thing with
        # its head turned politely away. It did exactly that.
        command = super().observe(seen)
        wrench = np.array(command.wrench, dtype=float)

        keep = 1.0 - (1.0 - float(self["slowestShare"])) * close["urgency"]
        away = wrap(seen.heading + self.going)
        speed = float(self["cruiseMs"]) * keep
        wanted_world = np.array([math.cos(away), math.sin(away), 0.0]) * speed
        wanted_body = seen.rotation.T @ wanted_world
        wrench[0] = self._newtons(0, self["speedKp"]
                                  * (float(wanted_body[0]) - float(seen.velocity[0])))
        wrench[1] = self._newtons(1, self["speedKp"]
                                  * (float(wanted_body[1]) - float(seen.velocity[1])))
        # And point where it is going, which is what a camera and a sonar
        # bolted to the front are for.
        wrench[5] = self.pilots.hold_heading(seen, away, self.dt)
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    def status(self) -> dict:
        said = super().status()
        said.update({"avoided": self.avoided, "closestM": self.closest,
                     "goingDeg": None if self.going is None
                     else round(math.degrees(self.going), 1)})
        return said
