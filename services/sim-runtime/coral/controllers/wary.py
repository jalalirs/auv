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
        # The water it may use, when somebody knows it: a tank's inside, a
        # harbour's quay lines. A detour chosen without it went round a pillar
        # on the side the glass was, and the vehicle spent two minutes pressed
        # against the glass trying to reach a point outside the tank.
        for side, default in (("fenceWestM", -1.0e4), ("fenceEastM", 1.0e4),
                              ("fenceSouthM", -1.0e4), ("fenceNorthM", 1.0e4)):
            self.declare(side, default, -1.0e4, 1.0e4, "m",
                         "where the water it may use ends, in the site's frame")
        self.declare("viaGiveUpS", 6.0, 1.0, 60.0, "s",
                     "how long a detour point may go unapproached before another is chosen")
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
        self.via_best, self.via_since = 0.0, 0.0
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

    def see_through(self, seen: Observation, fan: dict, reach: float) -> None:
        """Forget what a beam has just looked straight through.

        What is remembered is a wall until it is forgotten, and a fish that
        crossed a beam is not a wall: it was there for one ping, and kept for
        ten seconds it was a phantom the vehicle steered round long after it
        had swum off. So a remembered echo that sits inside a beam this ping,
        nearer than what the beam now returns (or anywhere in its reach, when
        it returns nothing), is gone — the beam has seen through where it was.
        A pillar is not forgotten this way: its echo is where the beam stops.
        This is what a sonar's occupancy map does with free space."""
        if not self.heard:
            return
        bearings = np.asarray(fan["bearingsRad"], dtype=float)
        ranges = np.asarray(fan["rangesM"], dtype=float)
        # Beams that touch: half the spacing either side of each.
        half = (0.5 * float(np.min(np.diff(np.sort(bearings)))) if len(bearings) > 1
                else math.radians(12.5))
        nose = float(self["sonarAheadM"])
        heading = float(seen.heading)
        x0 = float(seen.position[0]) + nose * math.cos(heading)
        y0 = float(seen.position[1]) + nose * math.sin(heading)
        points = np.array([(x, y) for _, x, y in self.heard])
        far = np.hypot(points[:, 0] - x0, points[:, 1] - y0)
        off = np.arctan2(points[:, 1] - y0, points[:, 0] - x0) - heading
        through = np.zeros(len(points), dtype=bool)
        for bearing, rangem in zip(bearings, ranges):
            inside = np.abs((off - bearing + np.pi) % (2 * np.pi) - np.pi) <= 0.8 * half
            short_of = (rangem - 0.05) if np.isfinite(rangem) else reach
            through |= inside & (far < short_of)
        if through.any():
            self.heard = [one for one, gone in zip(self.heard, through) if not gone]

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
            self.see_through(seen, fan, reach)
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

    # The map a detour is planned on: two centimetres a cell, which resolves a
    # pillar a hand across and is a few thousand cells for a tank.
    CELL_M = 0.02
    REPLAN_S = 0.5

    def plan(self, here, goal, wide: float):
        """A path from here to the goal that keeps the hull clear of everything
        remembered and inside the fence, or nothing if there is none.

        A grid, every echo grown by the clearance, the fence grown by most of
        it, and A* across what is left. One point beside the obstacle was not
        enough: when no single point fitted, the fallback backed away, and it
        backed away until the dive ran out.
        """
        import heapq

        cell = self.CELL_M
        west, east = float(self["fenceWestM"]), float(self["fenceEastM"])
        south, north = float(self["fenceSouthM"]), float(self["fenceNorthM"])
        span = np.array([here, goal])
        x0, x1 = max(west, span[:, 0].min() - 1.5), min(east, span[:, 0].max() + 1.5)
        y0, y1 = max(south, span[:, 1].min() - 1.5), min(north, span[:, 1].max() + 1.5)
        nx, ny = int((x1 - x0) / cell) + 1, int((y1 - y0) / cell) + 1
        if nx < 2 or ny < 2 or nx * ny > 400000:
            return None
        xs = x0 + np.arange(nx) * cell
        ys = y0 + np.arange(ny) * cell
        gx, gy = np.meshgrid(xs, ys)
        blocked = np.zeros((ny, nx), dtype=bool)
        if self.heard:
            pts = np.unique(np.round(np.array([(x, y) for _, x, y in self.heard]) / cell).astype(int), axis=0) * cell
            for x, y in pts:
                blocked |= (gx - x) ** 2 + (gy - y) ** 2 < wide * wide
        edge = 0.75 * wide
        blocked |= (gx < west + edge) | (gx > east - edge) | (gy < south + edge) | (gy > north - edge)

        def index(p):
            return (int(round((p[1] - y0) / cell)), int(round((p[0] - x0) / cell)))

        start, end = index(here), index(goal)
        if not (0 <= start[0] < ny and 0 <= start[1] < nx and 0 <= end[0] < ny and 0 <= end[1] < nx):
            return None
        # Where it already is and where it is going are allowed, however close
        # to something they are: a plan that cannot start is no plan.
        for j, i in (start, end):
            near = (gx - xs[i]) ** 2 + (gy - ys[j]) ** 2 < (0.6 * wide) ** 2
            blocked &= ~near
        steps = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
        cost = {start: 0.0}
        came = {}
        frontier = [(0.0, start)]
        while frontier:
            _, at = heapq.heappop(frontier)
            if at == end:
                break
            for dj, di, step in steps:
                nxt = (at[0] + dj, at[1] + di)
                if not (0 <= nxt[0] < ny and 0 <= nxt[1] < nx) or blocked[nxt]:
                    continue
                c = cost[at] + step
                if c < cost.get(nxt, 1e18):
                    cost[nxt] = c
                    came[nxt] = at
                    heapq.heappush(frontier, (c + math.hypot(nxt[0] - end[0], nxt[1] - end[1]), nxt))
        if end not in cost:
            return None
        path = [end]
        while path[-1] != start:
            path.append(came[path[-1]])
        path.reverse()
        return [np.array([xs[i], ys[j]]) for j, i in path]

    def detour(self, seen: Observation, command: Command):
        """Round what is remembered in the way of this leg, or nothing to do.

        When a vehicle-wide corridor along the leg holds something remembered,
        a path round it is planned on the map and followed a few centimetres
        at a time, re-planned twice a second as the sonar hears more; when the
        leg is clear again the route has the vehicle back. No path at all is a
        reason to stop, not to back away.
        """
        wide = float(self["clearanceM"])
        if wide <= 0.0 or self.at >= len(self.route):
            self.via = None
            return None
        here = np.array([float(seen.position[0]), float(seen.position[1])])
        point = self.route[self.at]
        goal = np.array([float(point.get("x", here[0])), float(point.get("y", here[1]))])
        distance = float(np.hypot(*(goal - here)))
        if distance < 1e-6 or not self.heard:
            self.via = None
            return None
        blocking = self.in_corridor(here, goal, wide, float(self["standOffM"]) + 2.0 * wide)
        if not blocking and self.via is None:
            return None
        if not blocking and self.via is not None and not self.in_corridor(here, goal, wide):
            self.via = None                          # the leg itself is clear again
            return None
        now = float(seen.t)
        if self.via is None or now - self.via_since >= self.REPLAN_S or self.via[1] != self.at:
            path = self.plan(here, goal, wide)
            self.via_since = now
            if path is None:
                self.via = (here.copy(), self.at)    # nowhere to go: stay put
            else:
                ahead = next((p for p in path if float(np.hypot(*(p - here))) >= 0.12), path[-1])
                self.via = (ahead, self.at)
                self.detours += 1
        return self._fly_to(seen, command, self.via[0])

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
