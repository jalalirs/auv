"""Flying a torpedo: one propeller, and fins that only work while it moves.

A vehicle like the REMUS 100 has no way to push sideways or straight up. It
steers the way a fish does, by going forward and leaning the water off its
tail: the rudder turns it, the stern planes pitch it, and the pitch is what
takes it up or down. Stop the propeller and the fins stop answering, because
the force on a fin is the square of the speed through the water times its
angle — so a torpedo cannot hold a station, cannot turn on the spot, and a
point it is told to reach is a point it passes through.

So this flies the same route the planner draws for every other vehicle, in
those terms:

  speed    the propeller holds a cruising speed through the water
  heading  the rudder turns it towards the next point, damped on the yaw rate
  depth    a nose-down angle in proportion to how much deeper it should be,
           which the stern planes hold, damped on the pitch rate

and at the end of the route it keeps going: it circles the last point, which
is what a torpedo waiting for somebody does.

It flies lines, not points. Chasing a point ten metres ahead with a circle
of eight it can turn on is a vehicle that overshoots every point and loops
back for it; a torpedo's guidance is line of sight instead (Fossen,
*Handbook of Marine Craft Hydrodynamics and Motion Control*, ch. 12): it aims
at a spot on the line from the last point to the next, a lookahead ahead of
where it is along it, so the error across the line closes smoothly. A leg is
done when the vehicle has come level with its end, near enough, or has passed
it; the task, which judges where the vehicle really is, says whether that was
close enough.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Controller, Observation


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class FinsController(Controller):
    """A route, flown on a propeller and four fins."""

    name = "fins"
    kind = "builtin"
    says = "Flies a torpedo: holds a speed on its propeller and steers and dives on its fins."

    def __init__(self, dt: float, mass_kg: float, drag: tuple[float, float],
                 most_forward_n: float, fin_most_rad: float) -> None:
        super().__init__()
        self.dt = dt
        # What the speed loop multiplies an acceleration by, and what the water
        # takes back at a speed: the hull's own, from its package.
        self.mass = float(mass_kg)
        self.drag_linear, self.drag_quadratic = (float(drag[0]), float(drag[1]))
        self.most_forward = max(1e-6, float(most_forward_n))
        self.fin_most = float(fin_most_rad)
        d = self.declare
        # The gains are not anybody's measurement. They are chosen so a REMUS
        # 100 at cruise turns and dives without overshooting much, and they are
        # parameters so a controller somebody writes can be compared with them.
        d("cruiseMs", 1.5, 0.3, 2.6, "m/s", "the speed it runs at through the water")
        d("speedKp", 0.5, 0.05, 4.0, "1/s", "propeller push per m/s short of the speed")
        d("headingKp", 1.0, 0.0, 6.0, "rad/rad", "rudder per radian of heading error")
        d("yawRateKd", 2.0, 0.0, 10.0, "rad/(rad/s)", "rudder per rad/s of yaw rate")
        d("depthKp", 0.1, 0.0, 1.0, "rad/m", "nose-down per metre too shallow")
        d("depthKi", 0.01, 0.0, 0.2, "rad/(m·s)", "nose-down per metre-second too shallow: the trim a buoyant hull needs")
        d("pitchMostDeg", 25.0, 5.0, 45.0, "°", "the steepest it dives or climbs")
        d("clearanceM", 3.0, 0.3, 20.0, "m",
          "the least height over the bottom it will hold, by its altimeter: over a reef the colonies stand a metre or two above it")
        d("lookaheadM", 18.0, 2.0, 200.0, "m",
          "how far along the line it aims: about twice the circle it can turn on")
        d("pitchKp", 1.5, 0.0, 8.0, "rad/rad", "stern planes per radian of pitch error")
        d("pitchRateKd", 1.0, 0.0, 10.0, "rad/(rad/s)", "stern planes per rad/s of pitch rate")
        d("arriveM", 5.0, 0.5, 50.0, "m", "how close counts as reached, when the route does not say")
        d("turnRateMostDegS", 10.0, 1.0, 60.0, "°/s", "the tightest it is expected to turn")
        self.route: list[dict] = []
        self.at = 0
        self.legs_done = 0
        self.holding = True
        self.distance = 0.0
        self.depth_wanted: float | None = None
        self.circling = False
        # Metre-seconds too shallow, kept: what a hull that floats needs leaned
        # against, which a proportional loop alone leaves as an offset.
        self.depth_owed = 0.0
        # The nearest it has been to the point it is going to.
        self.closest = math.inf
        self.leg_from: np.ndarray | None = None

    # ── what it is told ──────────────────────────────────────────────────────

    def steer(self, route) -> None:
        self.route = [dict(point) for point in (route or [])]
        self.leg_from = None
        self.at = 0
        self.legs_done = 0
        self.holding = not self.route
        self.circling = False
        self.closest = math.inf

    def engage(self, seen: Observation) -> None:
        if self.depth_wanted is None:
            self.depth_wanted = seen.depth

    def wants_back(self, seen: Observation) -> bool:
        return False

    def delivered(self, asked, given) -> None:
        return None

    def limit(self, authority) -> None:
        return None

    # ── the flying ───────────────────────────────────────────────────────────

    def _turning_m(self) -> float:
        """The radius of the tightest circle it is expected to fly at cruise."""
        return float(self["cruiseMs"]) / math.radians(float(self["turnRateMostDegS"]))

    def _reached(self, point: dict) -> bool:
        """Close enough, or past its closest approach inside its turning circle."""
        asked = float(point.get("arriveM", self["arriveM"]))
        if self.distance <= asked:
            return True
        passing = self.closest < 1.5 * self._turning_m() and self.distance > self.closest + 0.5
        self.closest = min(self.closest, self.distance)
        return passing

    def _depth_for(self, seen: Observation, point: dict | None) -> float:
        if point is not None and point.get("depthM") is not None:
            return float(point["depthM"])
        altitude = None if point is None else point.get("altitudeM")
        if altitude is not None and seen.floor is not None:
            return float(-(seen.floor + float(altitude)))
        return self.depth_wanted if self.depth_wanted is not None else seen.depth

    def observe(self, seen: Observation) -> Command:
        point = self.route[self.at] if self.at < len(self.route) else None
        if point is not None:
            target = np.array([float(point.get("x", seen.position[0])),
                               float(point.get("y", seen.position[1]))])
            if self.leg_from is None:
                self.leg_from = seen.position[:2].copy()
            flat = target - seen.position[:2]
            self.distance = float(np.hypot(*flat))
            leg = target - self.leg_from
            length = float(np.hypot(*leg))
            along_leg = leg / length if length > 1e-6 else flat / max(1e-6, self.distance)
            done_along = float(np.dot(seen.position[:2] - self.leg_from, along_leg))
            asked = float(point.get("arriveM", self["arriveM"]))
            if self.distance <= asked or (length > 1e-6 and done_along >= length - asked) or self._reached(point):
                self.closest = math.inf
                self.leg_from = target
                self.at += 1
                self.legs_done += 1
                self.depth_wanted = self._depth_for(seen, point)
                return self.observe(seen)
            self.holding = False
            # Line of sight: a spot on the line, a lookahead past where the
            # vehicle is level with along it.
            ahead = float(self["lookaheadM"])
            aim = self.leg_from + along_leg * min(length, max(0.0, done_along) + ahead)
            flat = aim - seen.position[:2]
        else:
            # The route is done. A torpedo cannot stop, so it circles where the
            # route ended — aiming at the point it has passed is a circle.
            self.holding = True
            self.circling = bool(self.route)
            last = self.route[-1] if self.route else None
            target = (np.array([float(last.get("x", seen.position[0])), float(last.get("y", seen.position[1]))])
                      if last is not None else seen.position[:2] + 10.0 * np.array(
                          [math.cos(seen.heading), math.sin(seen.heading)]))
            flat = target - seen.position[:2]
            self.distance = float(np.hypot(*flat))
        heading_wanted = math.atan2(float(flat[1]), float(flat[0]))
        depth_wanted = self._depth_for(seen, point)

        u = float(seen.velocity[0])
        q, r = float(seen.velocity[4]), float(seen.velocity[5])
        cruise = float(self["cruiseMs"])

        # Speed: the drag at cruise, and a push in proportion to what is short.
        push = (self.drag_linear * cruise + self.drag_quadratic * cruise * cruise
                + self.mass * float(self["speedKp"]) * (cruise - u))
        propeller = float(np.clip(push / self.most_forward, -1.0, 1.0))

        # Heading, on the rudder. A positive rudder turns it to port (yaw up).
        error = wrap(heading_wanted - seen.heading)
        rudder = float(self["headingKp"]) * error - float(self["yawRateKd"]) * r

        # Depth, through pitch, on the stern planes. Nose-down is positive
        # pitch in this z-up frame, and a positive plane angle pushes the tail
        # down, which lifts the nose.
        nose_down = math.asin(float(np.clip(-seen.rotation[2, 0], -1.0, 1.0)))
        most = math.radians(float(self["pitchMostDeg"]))
        # Never nearer the bottom than the altimeter allows: a torpedo over a
        # reef that holds a depth while the reef rises into it is a torpedo in
        # the coral, and a real one pulls up on its altimeter.
        if seen.floor is not None:
            deepest_safe = float(-(seen.floor + float(self["clearanceM"])))
            depth_wanted = min(depth_wanted, deepest_safe)
        short = depth_wanted - seen.depth
        # Only owed near the depth asked for. Summed all the way down from the
        # surface, it had built a lean that carried the vehicle four metres past
        # its depth and into the colonies under it.
        if abs(short) < 1.0:
            self.depth_owed = float(np.clip(self.depth_owed + short * self.dt, -30.0, 30.0))
        wanted = float(np.clip(float(self["depthKp"]) * short + float(self["depthKi"]) * self.depth_owed,
                               -most, most))
        planes = float(self["pitchKp"]) * (nose_down - wanted) + float(self["pitchRateKd"]) * q

        return Command(thrusters=np.array([propeller]),
                       actuators={"rudderRad": float(np.clip(rudder, -self.fin_most, self.fin_most)),
                                  "sternRad": float(np.clip(planes, -self.fin_most, self.fin_most))})

    def status(self) -> dict:
        return {"leg": self.at, "of": len(self.route), "legsDone": self.legs_done,
                "circling": self.circling, "nextM": round(self.distance, 1)}
