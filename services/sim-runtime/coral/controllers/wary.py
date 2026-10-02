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
        self.declare("standOffM", 6.0, 0.15, 30.0, "m",
                     "how close a return has to be before it is in the way")
        self.declare("aheadDeg", 50.0, 10.0, 90.0, "°",
                     "how far off the nose still counts as ahead")
        self.declare("leanDeg", 55.0, 5.0, 90.0, "°",
                     "how far it turns away at the closest it will get")
        self.declare("slowestShare", 0.25, 0.0, 1.0, "",
                     "how much of its speed it keeps when something is right there")
        self.declare("rememberS", 8.0, 0.0, 60.0, "s",
                     "how long an echo is kept once it has left the beams")
        self.declare("clearanceM", 0.0, 0.0, 5.0, "m",
                     "half the vehicle's width and a margin: the corridor kept clear "
                     "of anything remembered. Nought leaves it to the beams alone")
        self.declare("sonarAheadM", 0.0, 0.0, 2.0, "m",
                     "how far ahead of the vehicle's centre its sonar sits, so an echo is put "
                     "where it came from")
        self.declare("commitS", 4.0, 0.0, 30.0, "s",
                     "how long it keeps the way round it chose")
        self.avoided = 0
        self.closest = None
        # The way round it picked, and when. A vehicle that reconsiders every
        # fifth of a second never finishes a turn.
        self.going = None
        self.chose_at = None
        # What the sonar has heard, as places in the water, for a while. Three
        # beams with gaps between them lose a thing the moment the vehicle
        # turns for it: a pillar thirteen centimetres across fell between the
        # beams half a second after it was seen, the way looked clear, and the
        # route took the vehicle straight through it.
        self.heard: list[tuple[float, float, float]] = []
        self.detours = 0
        self.via = None
        self._last_fan = None

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
        near = float(said.get("rangeM", 0.0))
        # The nearest return *ahead*, not the nearest return and then a check
        # that it is ahead. In a tank the beams either side hear the side glass
        # before anything else, so the nearest was always the glass, always
        # off the nose, and a rock pillar dead ahead never counted: the first
        # tank round trip flew into it with the sonar pinging the whole way.
        fan = getattr(seen, "sonar", None)
        if fan:
            bearings = np.asarray(fan["bearingsRad"], dtype=float)
            ranges = np.asarray(fan["rangesM"], dtype=float)
            ahead = (np.abs(bearings) <= math.radians(float(self["aheadDeg"]))) & np.isfinite(ranges)
            if not ahead.any():
                return None
            at = int(np.flatnonzero(ahead)[np.argmin(ranges[ahead])])
            near, bearing = float(ranges[at]), float(bearings[at])
        elif abs(bearing) > math.radians(float(self["aheadDeg"])):
            return None
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
        # Of two gaps as wide, the one with more water in it: with three beams
        # the two sides are each a gap of one, and taking the first found sent
        # the vehicle towards whichever side was listed first, glass or not.
        room = np.where(np.isfinite(ranges), ranges, np.inf)
        best, run, start, open_ = (0, None, -1.0), 0, 0, 0.0
        for i, ok in enumerate(clear):
            if ok:
                if run == 0:
                    start, open_ = i, 0.0
                run += 1
                open_ += min(float(room[i]), 1e6)
                if (run, open_) > (best[0], best[2]):
                    best = (run, (start, i), open_)
            else:
                run = 0
        if best[1] is None:
            return -math.copysign(math.radians(float(self["leanDeg"])),
                                  close["bearingRad"] or 1.0)
        first, last = best[1]
        return float((bearings[first] + bearings[last]) / 2.0)

    def remember(self, seen: Observation) -> None:
        """Every echo close enough to matter, as a point in the world."""
        fan = getattr(seen, "sonar", None)
        keep = float(self["rememberS"])
        now = float(seen.t)
        # Once per ping, not once per step. The fan is the sonar's last sweep
        # and it is handed over on every one of two hundred steps a second;
        # stored each time, ten seconds of memory held one second of echoes
        # in twenty copies, and a pillar was forgotten a second after it was
        # last heard.
        fresh = fan is not None and not (
            self._last_fan is not None
            and np.array_equal(np.asarray(fan["rangesM"], dtype=float), self._last_fan, equal_nan=True))
        if fresh:
            self._last_fan = np.asarray(fan["rangesM"], dtype=float).copy()
        if fan and fresh and keep > 0.0:
            reach = max(1.0, 3.0 * float(self["standOffM"]))
            for bearing, rangem in zip(np.asarray(fan["bearingsRad"], dtype=float),
                                       np.asarray(fan["rangesM"], dtype=float)):
                if np.isfinite(rangem) and rangem < reach:
                    way = float(seen.heading) + float(bearing)
                    nose = float(self["sonarAheadM"])
                    x0 = float(seen.position[0]) + nose * math.cos(float(seen.heading))
                    y0 = float(seen.position[1]) + nose * math.sin(float(seen.heading))
                    self.heard.append((now, x0 + float(rangem) * math.cos(way),
                                       y0 + float(rangem) * math.sin(way)))
        self.heard = [one for one in self.heard if now - one[0] <= keep][-3000:]

    def blocked(self, seen: Observation, towards: float, reach: float) -> tuple[bool, float]:
        """Whether a remembered echo is in a vehicle-wide corridor that way, and
        on which side of it the nearest one is."""
        wide = float(self["clearanceM"])
        u = np.array([math.cos(towards), math.sin(towards)])
        across = np.array([-u[1], u[0]])
        nearest, side = None, 0.0
        for _, x, y in self.heard:
            rel = np.array([x - float(seen.position[0]), y - float(seen.position[1])])
            along = float(rel @ u)
            off = float(rel @ across)
            if 0.0 < along < reach and abs(off) < wide:
                if nearest is None or along < nearest:
                    nearest, side = along, off
        return nearest is not None, side

    def in_corridor(self, here, there, wide: float, reach: float | None = None):
        """Remembered echoes in a vehicle-wide corridor from here towards there."""
        flat = np.asarray(there, dtype=float) - here
        distance = float(np.hypot(*flat))
        if distance < 1e-6:
            return []
        u = flat / distance
        across = np.array([-u[1], u[0]])
        reach = distance if reach is None else min(distance, reach)
        out = []
        for _, x, y in self.heard:
            rel = np.array([x, y]) - here
            along, off = float(rel @ u), float(rel @ across)
            if 0.0 < along < reach and abs(off) < wide:
                out.append((along, off, np.array([x, y])))
        return out

    def detour(self, seen: Observation, command: Command):
        """Round what is remembered in the way of this leg, or nothing to do.

        A point beside the obstacle, reachable by a clear corridor, flown to
        and then the leg again. Deciding a heading afresh every step dithered
        for ten seconds in front of a pillar half a metre away; and close in
        there is no deciding at all, because a Ping2 hears nothing nearer than
        0.3 m. So the choice is made while the thing is still heard, kept while
        the way to it stays clear, and made again the moment it does not.
        """
        wide = float(self["clearanceM"])
        if wide <= 0.0 or self.at >= len(self.route):
            self.via = None
            return None
        here = np.array([float(seen.position[0]), float(seen.position[1])])
        point = self.route[self.at]
        goal = np.array([float(point.get("x", here[0])), float(point.get("y", here[1]))])
        if self.via is not None:
            via, leg = self.via
            if (leg != self.at or float(np.hypot(*(via - here))) < 0.05
                    or self.in_corridor(here, via, wide)):
                self.via = None
            else:
                return self._fly_to(seen, command, via)
        flat = goal - here
        distance = float(np.hypot(*flat))
        if distance < 1e-6 or not self.heard:
            return None
        u = flat / distance
        across = np.array([-u[1], u[0]])
        blocking = self.in_corridor(here, goal, wide, float(self["standOffM"]) + 2.0 * wide)
        if not blocking:
            return None
        nearest = min(b[0] for b in blocking)
        cluster = [b for b in blocking if b[0] < nearest + 0.15]
        centre = np.mean([b[2] for b in cluster], axis=0)
        lean = float(np.mean([b[1] for b in cluster]))
        sides = (-1.0, 1.0) if lean > 0 else (1.0, -1.0)     # away from it first
        chosen = None
        for ahead in (0.0, -0.1, 0.1):
            for sign in sides:
                via = centre + across * sign * (wide + 0.08) + u * ahead
                fits = all(float(np.hypot(x - via[0], y - via[1])) >= wide for _, x, y in self.heard)
                if fits and not self.in_corridor(here, via, wide):
                    chosen = via
                    break
            if chosen is not None:
                break
        if chosen is None:
            chosen = here - u * 0.15                      # nowhere fits: back off
        self.via = (chosen, self.at)
        self.detours += 1
        return self._fly_to(seen, command, chosen)

    def _fly_to(self, seen: Observation, command: Command, via) -> Command:
        here = np.array([float(seen.position[0]), float(seen.position[1])])
        flat = np.asarray(via, dtype=float) - here
        distance = float(np.hypot(*flat))
        towards = math.atan2(float(flat[1]), float(flat[0]))
        speed = float(self["cruiseMs"]) * min(1.0, distance / max(1e-6, float(self["easeM"])))
        wanted_body = seen.rotation.T @ (np.array([math.cos(towards), math.sin(towards), 0.0]) * speed)
        wrench = np.array(command.wrench, dtype=float)
        wrench[0] = self._newtons(0, self["speedKp"] * (float(wanted_body[0]) - float(seen.velocity[0])))
        wrench[1] = self._newtons(1, self["speedKp"] * (float(wanted_body[1]) - float(seen.velocity[1])))
        wrench[5] = self.pilots.hold_heading(seen, towards, self.dt)
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    def observe(self, seen: Observation) -> Command:
        self.remember(seen)
        planned = super().observe(seen)
        round_it = self.detour(seen, planned)
        if round_it is not None:
            return round_it
        close = self.in_the_way(seen)
        if close is None:
            self.closest = None
            self.going = None
            self.chose_at = None
            return planned

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
        command = planned
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
                     "detours": self.detours, "remembered": len(self.heard),
                     "goingDeg": None if self.going is None
                     else round(math.degrees(self.going), 1)})
        return said
