"""Flying a route: the controller that makes a task mean what it says.

Between the hold, which stays where it is put, and a stack somebody wrote,
there was nothing — so a dive with a task sat exactly where it started and
scored zero, and every task on the dive page was a thing that watched rather
than a thing that happened.

This is the platform's own answer to a route. It is deliberately ordinary:
turn towards the next point, go at a speed that eases off as you arrive, hold
the depth the point asks for or the altitude the leg asks for, and when the
route runs out, hold. Nothing here is clever, and that is the point — it is
the reference a written controller is measured against, and the reason a task
can be flown by somebody who has not written one.

It borrows the hold's autopilots for depth and heading, so a route flown by
this and a station held by that behave the same way about the same things.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Controller, Observation
from .hold import Autopilots, wrap


class PursueController(Controller):
    """Follow a route of points, and hold at the end of it."""

    name = "pursue"
    kind = "builtin"
    says = "Flies the route a task asks for: turn, run, arrive, hold."

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float) -> None:
        super().__init__()
        self.capability = np.asarray(capability, dtype=float)
        self.mass = np.asarray(mass, dtype=float)
        self.dt = dt
        self.pilots = Autopilots(self, mass, capability, trim_n)
        self.declare("cruiseMs", 0.4, 0.05, 1.5, "m/s", "how fast it runs between points")
        self.declare("speedKp", 1.2, 0.1, 6.0, "1/s", "surge per metre per second of speed error")
        self.declare("easeM", 2.0, 0.2, 20.0, "m", "how far out it starts slowing for the point")
        self.declare("arriveM", 1.0, 0.1, 10.0, "m", "how close counts as reached")
        self.declare("faceFirstDeg", 45.0, 0.0, 180.0, "°",
                     "turn towards the point before running at it, up to this much off")
        self.route: list[dict] = []
        self.at = 0
        self.station: np.ndarray | None = None
        self.station_depth: float | None = None
        self.distance = 0.0
        self.bearing = 0.0
        self.holding = True
        self.legs_done = 0
        self.waiting_since: float | None = None

    # ── what it is told ──────────────────────────────────────────────────────

    def steer(self, route) -> None:
        """A new route: a list of points, each with x, y and a depth or altitude.

        Given in world metres, because by the time a route exists the dive knows
        where it is. What the point says about height wins: depthM if it has
        one, altitudeM if it wants to fly off the bottom, otherwise it keeps
        whatever depth it was already holding.
        """
        self.route = [dict(point) for point in (route or [])]
        self.at = 0
        self.legs_done = 0
        self.waiting_since = None
        self.holding = not self.route

    def engage(self, seen: Observation) -> None:
        self.station = seen.position[:2].copy()
        self.station_depth = seen.depth
        self.pilots.reset()
        if not self.route:
            self.holding = True

    def _adrift(self, seen: Observation) -> bool:
        """Whether the vehicle has come off the end of its route.

        Judged with hysteresis, and against where the vehicle believes it is,
        like everything else a controller does: going back for a centimetre
        would have it setting off again every time a fix landed.
        """
        last = self.route[-1]
        flat = np.array([float(last.get("x", seen.position[0])),
                         float(last.get("y", seen.position[1]))]) - seen.position[:2]
        away = float(np.hypot(*flat))
        arrive = float(last.get("arriveM", self["arriveM"]))
        return away > max(2.0 * arrive, arrive + 1.0)

    def limit(self, authority: np.ndarray) -> None:
        self.capability = np.asarray(authority, dtype=float)
        self.pilots.limit(authority)

    # ── the flying ───────────────────────────────────────────────────────────

    def observe(self, seen: Observation) -> Command:
        point = self.route[self.at] if self.at < len(self.route) else None
        if point is None:
            # The route is flown, and staying at the end of it is the job —
            # but only while the vehicle is still there. A fix that arrives
            # after the last leg can move the vehicle's idea of itself by
            # several metres, and until now nothing acted on that: the hold
            # holds a position, not a goal, so a return that was corrected
            # after arriving sat seven metres from home for the rest of the
            # dive with a controller that thought it was there.
            #
            # So the last point is still a point. Drift far enough off it and
            # the route is not finished after all.
            if self.route and self._adrift(seen):
                self.at = len(self.route) - 1
                self.holding = False
                self.legs_done = max(0, self.legs_done - 1)
                return self.observe(seen)
            return self._hold(seen)

        target = np.array([float(point.get("x", seen.position[0])),
                           float(point.get("y", seen.position[1]))])
        flat = target - seen.position[:2]
        self.distance = float(np.hypot(*flat))
        # A leg may ask for more than the route's usual care. Docking is the
        # reason: a station is a forty-centimetre target approached slowly, and
        # a controller that calls a metre "arrived" stops a metre short of it
        # every time and never knows why.
        arrive = float(point.get("arriveM", self["arriveM"]))
        cruise = min(float(self["cruiseMs"]), float(point.get("speedMs", self["cruiseMs"])))
        ease = min(float(self["easeM"]), float(point.get("easeM", self["easeM"])))
        if self.distance <= arrive and self._deep_enough(seen, point):
            # A leg may ask to be stayed at. Sampling a colony is ten seconds
            # of holding still over it, and a route that arrives and leaves
            # again immediately does the visiting without doing the work.
            stay = float(point.get("holdS", 0.0))
            if stay > 0.0:
                if self.waiting_since is None:
                    self.waiting_since = float(seen.t)
                    self.station = seen.position[:2].copy()
                    self.station_depth = self._depth_for(seen, point)
                if float(seen.t) - self.waiting_since < stay:
                    return self._hold(seen, at_depth=self.station_depth)
            self.waiting_since = None
            self.at += 1
            self.legs_done += 1
            self.station = seen.position[:2].copy()
            self.station_depth = seen.depth
            return self.observe(seen)

        self.holding = False
        self.bearing = math.atan2(float(flat[1]), float(flat[0]))

        # Where the nose points. Usually along the way it is going; but a leg
        # may name something to keep looking at, which is what an inspection
        # is — going round a thing while facing it — and the vehicle then
        # crabs along its route rather than driving down it.
        look = point.get("facing")
        if isinstance(look, dict):
            towards = np.array([float(look.get("x", target[0])) - float(seen.position[0]),
                                float(look.get("y", target[1])) - float(seen.position[1])])
            heading_wanted = math.atan2(float(towards[1]), float(towards[0]))
            easing = 1.0
        else:
            heading_wanted = self.bearing
            # Turn towards it before running at it. A vehicle that drives while
            # badly off heading arrives sideways, and on a frame with vectored
            # thrusters that is a long slow arc rather than a straight line.
            off = wrap(self.bearing - seen.heading)
            easing = max(0.0, 1.0 - abs(off) / max(1e-6, math.radians(self["faceFirstDeg"])))

        speed = cruise * min(1.0, self.distance / max(1e-6, ease)) * easing
        # The velocity it wants, in the world, turned into the vehicle's own
        # frame: surge and sway together, so that where it points and where it
        # goes are two separate questions.
        wanted_world = np.array([flat[0], flat[1], 0.0]) / max(1e-6, self.distance) * speed
        wanted_body = seen.rotation.T @ wanted_world
        surge = self._newtons(0, self["speedKp"] * (float(wanted_body[0]) - float(seen.velocity[0])))
        sway = self._newtons(1, self["speedKp"] * (float(wanted_body[1]) - float(seen.velocity[1])))
        yaw = self.pilots.hold_heading(seen, heading_wanted, self.dt)
        heave = self.pilots.hold_depth(seen, self._depth_for(seen, point), self.dt)
        wrench = np.array([surge, sway, heave, 0.0, 0.0, yaw])
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    def _hold(self, seen: Observation, at_depth: float | None = None) -> Command:
        """Stay where it is: the route is flown, or this leg is being waited at."""
        self.holding = at_depth is None
        self.distance = 0.0
        if self.station is None:
            self.engage(seen)
        heave = self.pilots.hold_depth(seen, at_depth if at_depth is not None
                                       else (self.station_depth or seen.depth), self.dt)
        yaw = self.pilots.hold_heading(seen, seen.heading, self.dt)
        surge, sway = self.pilots.hold_position(seen, self.station, self.dt)
        wrench = np.array([surge, sway, heave, 0.0, 0.0, yaw])
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    def _depth_for(self, seen: Observation, point: dict) -> float:
        """The depth this leg wants: its own, or an altitude over the bottom."""
        if point.get("depthM") is not None:
            return float(point["depthM"])
        altitude = point.get("altitudeM")
        if altitude is not None and seen.floor is not None:
            return float(-(seen.floor + float(altitude)))
        return self.station_depth if self.station_depth is not None else seen.depth

    def _deep_enough(self, seen: Observation, point: dict) -> bool:
        """Whether the height this leg asked for has been reached as well.

        Only for a leg that names a depth. A leg that names an altitude is
        flying a carpet over the bottom and is never waited on: it would stop
        the route every time the ground rose.
        """
        if point.get("depthM") is None:
            return True
        arrive = float(point.get("arriveM", self["arriveM"]))
        return abs(seen.depth - float(point["depthM"])) <= max(0.35, arrive)

    def _newtons(self, axis: int, acceleration: float) -> float:
        most = float(self.capability[axis])
        return float(np.clip(acceleration * self.mass[axis], -most, most))

    def status(self) -> dict:
        return {"leg": self.at, "of": len(self.route), "legsDone": self.legs_done,
                "waitingAtTheLeg": self.waiting_since is not None,
                "toGoM": round(self.distance, 2),
                "bearingDeg": round(math.degrees(self.bearing) % 360.0, 1),
                "holding": self.holding}
