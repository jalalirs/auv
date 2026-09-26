"""Getting somewhere, and staying there.

The tasks whose whole content is a position and a tolerance. Everything else in
this package is built on them: a survey is lanes, a section is a sawtooth, an
outplant is a visit and a wait, and all of those are this file's arithmetic with
a purpose attached.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Task, wrap


class HoldStation(Task):
    kind = "hold-station"
    name = "Hold station"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.seconds = float(objective.get("seconds", 60.0))
        self.radius = float(objective.get("radiusM", 0.5))
        self.band = float(objective.get("depthBandM", 0.3))
        self.within = 0.0
        self.last_t: float | None = None
        self.off = 0.0
        self.worst = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        dt = 0.0 if self.last_t is None else elapsed - self.last_t
        self.last_t = elapsed
        self.off = float(np.hypot(*(position[:2] - self.began_at[:2])))
        depth_off = abs(float(-position[2]) - self.start_depth())
        self.worst = max(self.worst, self.off)
        if self.off <= self.radius and depth_off <= self.band:
            self.within += dt
        if elapsed >= self.seconds:
            self.done = True

    def score(self) -> float:
        return min(1.0, self.within / self.seconds) if self.seconds > 0 else 0.0

    def says(self) -> str:
        return f"{self.within:.0f} of {self.seconds:.0f} s on station, {self.off:.2f} m off"

    def detail(self) -> dict:
        return {"secondsOnStation": round(self.within, 1), "secondsAsked": self.seconds,
                "offStationM": round(self.off, 3), "worstOffM": round(self.worst, 3),
                "radiusM": self.radius, "depthBandM": self.band}

    def geometry(self) -> dict:
        return {"circle": {"x": float(self.began_at[0]), "y": float(self.began_at[1]), "radiusM": self.radius}}

    def goal(self) -> dict:
        return {"kind": "hold", "at": [float(v) for v in self.began_at],
                "radiusM": self.radius}


class Waypoints(Task):
    kind = "waypoints"
    name = "Waypoints"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.radius = float(objective.get("radiusM", 1.0))
        self.limit = float(objective.get("timeLimitS", 300.0))
        ahead = self.ahead()
        right = (ahead[1], -ahead[0])
        self.points: list[np.ndarray] = []
        for point in objective.get("points", [{"dx": 8, "dy": 0}, {"dx": 8, "dy": 8}, {"dx": 0, "dy": 8}, {"dx": 0, "dy": 0}]):
            dx, dy = float(point.get("dx", 0.0)), float(point.get("dy", 0.0))
            depth = point.get("depthM")
            z = -float(depth) if depth is not None else float(self.began_at[2])
            self.points.append(np.array([
                self.began_at[0] + dx * ahead[0] + dy * right[0],
                self.began_at[1] + dx * ahead[1] + dy * right[1], z]))
        self.reached = 0
        self.reached_at: list[float] = []
        self.distance = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.reached < len(self.points):
            target = self.points[self.reached]
            self.distance = float(np.linalg.norm(position - target))
            if self.distance <= self.radius:
                self.reached += 1
                self.reached_at.append(round(elapsed, 1))
        if self.reached >= len(self.points) or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if not self.points:
            return 0.0
        base = self.reached / len(self.points)
        # Over time is half marks: the points were reached, the mission was not.
        return base if self.elapsed() <= self.limit or self.reached < len(self.points) else base * 0.5

    def says(self) -> str:
        if self.reached >= len(self.points):
            return f"all {len(self.points)} reached in {self.elapsed():.0f} s"
        return f"{self.reached} of {len(self.points)} reached, next {self.distance:.1f} m away"

    def detail(self) -> dict:
        return {"reached": self.reached, "of": len(self.points), "reachedAtS": self.reached_at,
                "radiusM": self.radius, "timeLimitS": self.limit, "nextM": round(self.distance, 2)}

    def geometry(self) -> dict:
        return {"points": [{"x": float(p[0]), "y": float(p[1]), "depthM": float(-p[2])} for p in self.points],
                "reached": self.reached}

    def goal(self) -> dict:
        return {"kind": "visit", "points": [[float(v) for v in p] for p in self.points],
                "radiusM": self.radius}

    def failed(self) -> bool:
        return self.done and self.reached < len(self.points)


class Transect(Task):
    kind = "transect"
    name = "Transect"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.length = float(objective.get("lengthM", 20.0))
        self.altitude = float(objective.get("altitudeM", 2.0))
        self.band = float(objective.get("altitudeBandM", 0.5))
        self.tolerance = math.radians(float(objective.get("headingToleranceDeg", 10.0)))
        self.ahead_xy = np.array(self.ahead())
        self.line_heading = math.atan2(self.ahead_xy[1], self.ahead_xy[0])
        # Where this leg's line starts, and which way it runs — both settled
        # when the leg starts and not when the dive did.
        #
        # This was `began_at`, which inside a mission is where the *dive*
        # began and not where the previous stage left the vehicle. `Reach`
        # has carried a comment about exactly this for months; a transect
        # did not, and nothing noticed because until there was a mission
        # with more than one stage in it the two were the same place. After
        # a leg that had already run along the line, `along` began at some
        # positive number, the transect ended immediately, and it scored
        # zero for a reason that had nothing to do with the flying.
        #
        # An unstated heading is the one the vehicle has when the leg
        # begins, which is also what it was before for a dive of one stage.
        self.stated_heading = objective.get("headingDeg") is not None
        self.from_at: np.ndarray | None = None
        self.along = 0.0
        self.good = 0.0
        self.last_along: float | None = None
        self.altitude_now: float | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.from_at is None:
            self.from_at = position[:2].copy()
            if not self.stated_heading:
                self.line_heading = float(heading)
                self.ahead_xy = np.array([math.cos(heading), math.sin(heading)])
        along = float(np.dot(position[:2] - self.from_at, self.ahead_xy))
        along = max(0.0, min(self.length, along))
        self.altitude_now = None if floor is None else float(position[2] - floor)
        in_band = self.altitude_now is not None and abs(self.altitude_now - self.altitude) <= self.band
        on_heading = abs(wrap(heading - self.line_heading)) <= self.tolerance
        if self.last_along is not None and along > self.last_along and in_band and on_heading:
            self.good += along - self.last_along
        self.last_along = along
        self.along = max(self.along, along)
        if self.along >= self.length - 0.05 or elapsed >= float(self.objective.get("timeLimitS", 1e9)):
            self.done = True

    def score(self) -> float:
        return min(1.0, self.good / self.length) if self.length > 0 else 0.0

    def says(self) -> str:
        alt = "—" if self.altitude_now is None else f"{self.altitude_now:.2f} m"
        return f"{self.along:.1f} of {self.length:.0f} m along, {self.good:.1f} m within band, altitude {alt}"

    def detail(self) -> dict:
        return {"alongM": round(self.along, 2), "goodM": round(self.good, 2), "lengthM": self.length,
                "altitudeM": self.altitude, "altitudeBandM": self.band,
                "headingToleranceDeg": round(math.degrees(self.tolerance), 1)}

    def starts_at(self) -> np.ndarray:
        """Where the line begins: where this leg did, once it has."""
        return self.began_at[:2] if self.from_at is None else self.from_at

    def geometry(self) -> dict:
        start = self.starts_at()
        end = start + self.ahead_xy * self.length
        return {"line": [{"x": float(start[0]), "y": float(start[1])},
                         {"x": float(end[0]), "y": float(end[1])}]}

    def goal(self) -> dict:
        start = self.starts_at()
        end = start + self.ahead_xy * self.length
        return {"kind": "line", "from": [float(v) for v in start],
                "to": [float(end[0]), float(end[1])], "altitudeM": self.altitude}


class Reach(Task):
    """Get to a point. The one everything else is built on.

    Scored on arriving, and then on how well: a vehicle that gets there by the
    short way, quickly, is worth more than one that wanders and worth much more
    than one that does not arrive. The path it took is compared with the
    straight line, which on a reef is a generous comparison — the short way
    over a spur is not the short way through the water — so a score near one
    is a vehicle that went almost directly.
    """

    kind = "reach"
    name = "Reach a point"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.radius = float(objective.get("radiusM", 1.5))
        self.limit = float(objective.get("timeLimitS", 600.0))
        self.target = self.somewhere(objective.get("target") or objective,
                                     self.out_from_start(float(objective.get("dx", 20.0)),
                                                         float(objective.get("dy", 0.0)),
                                                         objective.get("depthM")))
        # How far there is to go, measured from where this leg starts rather
        # than from where the dive did. In a mission the two are not the same
        # place, and scoring a stage on the dive's start makes a leg back to
        # where you began look like a leg to nowhere.
        self.straight = float(np.linalg.norm(self.target - self.began_at))
        self.from_at: np.ndarray | None = None
        self.travelled = 0.0
        self.last: np.ndarray | None = None
        self.distance = self.straight
        self.arrived = False
        self.arrived_at = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.from_at is None:
            self.from_at = position.copy()
            self.straight = float(np.linalg.norm(self.target - self.from_at))
        if self.last is not None:
            self.travelled += float(np.linalg.norm(position - self.last))
        self.last = position.copy()
        self.distance = float(np.linalg.norm(position - self.target))
        if self.distance <= self.radius and not self.arrived:
            self.arrived = True
            self.arrived_at = elapsed
            self.done = True
        if elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if not self.arrived:
            # Credit for the ground it did close, so a controller that goes the
            # wrong way and one that nearly makes it are not the same number.
            closed = max(0.0, self.straight - self.distance) / max(1e-6, self.straight)
            return 0.5 * min(1.0, closed)
        if self.straight <= self.radius:
            return 1.0          # it was already there; arriving is the whole job
        directness = min(1.0, self.straight / max(1e-6, self.travelled))
        return 0.5 + 0.5 * directness

    def says(self) -> str:
        if self.arrived:
            return f"there in {self.arrived_at:.0f} s, {self.travelled:.0f} m travelled for {self.straight:.0f} m"
        return f"{self.distance:.1f} m to go of {self.straight:.0f} m"

    def detail(self) -> dict:
        return {"arrived": self.arrived, "toGoM": round(self.distance, 2),
                "straightM": round(self.straight, 2), "travelledM": round(self.travelled, 2),
                "directness": round(min(1.0, self.straight / max(1e-6, self.travelled)), 3),
                "radiusM": self.radius, "timeLimitS": self.limit}

    def geometry(self) -> dict:
        return {"points": [{"x": float(self.target[0]), "y": float(self.target[1]),
                            "depthM": float(-self.target[2])}],
                "reached": 1 if self.arrived else 0,
                "line": [{"x": float(self.began_at[0]), "y": float(self.began_at[1])},
                         {"x": float(self.target[0]), "y": float(self.target[1])}]}

    def goal(self) -> dict:
        return {"kind": "go", "to": [float(v) for v in self.target], "radiusM": self.radius}

    def failed(self) -> bool:
        return self.done and not self.arrived


class Descend(Task):
    """Get down to the bottom, on the site, under control.

    The phase of a dive nobody had modelled, and the one an operator spends
    the most breath on. A vehicle enters the water above the site and has to
    arrive at working altitude *over the site*, and between those two moments
    it is being set sideways by whatever the current is doing and it cannot
    see the bottom to know.

    Three things are scored, and they are the three an operator argues about:

      **Did it arrive** — at the altitude it was told, and in the time there
      was. Everything after this assumes a vehicle that is down.

      **Did it land on the mark.** A descent is a drift problem: a tenth of a
      knot over a hundred metres of water column is twenty metres downstream,
      and the site is forty metres across. This is where a dive plan is won
      or lost and no log from a real vehicle can tell you how badly, because
      the vehicle does not know where it actually was.

      **Under control.** A vehicle that arrives by falling arrives badly: it
      stirs the bottom it came to photograph, and a manipulator wants a hull
      that is already still.

    And one thing is reported rather than scored, because it is the fact the
    rest of the dive's navigation rests on: **how much of the descent was
    flown blind**. A Doppler log has a range, and above it there is no bottom
    track at all — the vehicle is dead reckoning on a flight model through
    the part of the dive where the current is strongest. The metres it
    descended before lock, and the metres it moved sideways in them, are the
    honest size of the error every later leg inherits.
    """

    kind = "descend"
    name = "Descend to the bottom"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        # Where to stop: an altitude off the bottom is what an operator says,
        # and a depth is what somebody says when there is no bottom to speak
        # of. Altitude wins when both are given, because the bottom is the
        # thing being worked on.
        self.altitude = objective.get("toAltitudeM")
        self.altitude = None if self.altitude is None else float(self.altitude)
        self.depth = objective.get("toDepthM")
        self.depth = None if self.depth is None else float(self.depth)
        if self.altitude is None and self.depth is None:
            self.altitude = 3.0
        self.band = float(objective.get("bandM", 1.0))
        # How far from the mark it may land and still count. Wider than a
        # reach's radius on purpose: nobody expects a descent to be placed to
        # a metre, and pretending otherwise scores every real descent zero.
        self.within = float(objective.get("withinM", 5.0))
        # What counts as under control on arrival. A vehicle still making
        # half a metre a second at the bottom is a vehicle about to hit it.
        self.rate = float(objective.get("rateMs", 0.4))
        self.limit = float(objective.get("timeLimitS", 900.0))
        # Where it was meant to come down, in the world. The entry point by
        # default, which is the operational case: the boat holds station over
        # the site and the vehicle is meant to arrive under itself.
        self.mark = self.somewhere(objective.get("over") or objective.get("mark"),
                                   self.began_at.copy())[:2]

        self.arrived = False
        self.arrived_at = 0.0
        self.off_the_mark = 0.0
        self.worst_rate = 0.0
        self.rate_on_arrival = 0.0
        self.altitude_now: float | None = None
        self.depth_now = 0.0
        # The blind part. `locked` is the navigation's own answer, handed
        # down; the fallback is "we cannot say", which is reported as such
        # rather than guessed from a range this task would have to keep a
        # second copy of.
        self.began_depth: float | None = None
        self.locked_at_depth: float | None = None
        self.locked_at_altitude: float | None = None
        self.blind_from: np.ndarray | None = None
        self.blind_moved: float | None = None
        self.was_told = False
        self.last: np.ndarray | None = None
        self.last_t: float | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        depth = float(-position[2])
        if self.began_depth is None:
            self.began_depth = depth
            self.blind_from = position[:2].copy()
        self.depth_now = depth
        self.altitude_now = None if floor is None else float(position[2] - floor)

        # How fast it is going down, from the truth rather than from a
        # command: a vehicle whose thrusters are saturated is not descending
        # at the rate it asked for.
        if self.last is not None and self.last_t is not None and elapsed > self.last_t:
            down = (self.last[2] - float(position[2])) / (elapsed - self.last_t)
            self.worst_rate = max(self.worst_rate, down)
            self.rate_on_arrival = down
        self.last = position.copy()
        self.last_t = elapsed

        # When the log found the bottom, and how far the water had carried it
        # by then. Asked of the navigation, not worked out here.
        if self.locked and self.locked_at_depth is None:
            self.was_told = True
            self.locked_at_depth = depth
            self.locked_at_altitude = self.altitude_now
            if self.blind_from is not None:
                self.blind_moved = float(np.linalg.norm(position[:2] - self.blind_from))

        self.off_the_mark = float(np.linalg.norm(position[:2] - self.mark))
        if not self.arrived and self.there(depth):
            self.arrived = True
            self.arrived_at = elapsed
            self.done = True
        if elapsed >= self.limit:
            self.done = True

    def there(self, depth: float) -> bool:
        if self.altitude is not None:
            return (self.altitude_now is not None
                    and abs(self.altitude_now - self.altitude) <= self.band)
        return abs(depth - float(self.depth)) <= self.band

    def score(self) -> float:
        if not self.arrived:
            # Credit for the water column it did get through, so a vehicle
            # that stopped at forty metres of a hundred and one that never
            # left the surface are not the same number.
            if self.altitude is not None and self.altitude_now is not None:
                left = max(0.0, self.altitude_now - self.altitude)
                whole = max(1e-6, (self.altitude_now if self.began_depth is None
                                   else abs(self.depth_now - self.began_depth) + left))
            else:
                left = abs(self.depth_now - float(self.depth or 0.0))
                whole = max(1e-6, abs(float(self.depth or 0.0) - (self.began_depth or 0.0)))
            return 0.5 * max(0.0, min(1.0, 1.0 - left / whole))
        # Arrived. The rest is where it landed and how hard.
        placed = max(0.0, 1.0 - self.off_the_mark / max(1e-6, self.within))
        gentle = 1.0 if self.rate_on_arrival <= self.rate else max(
            0.0, 1.0 - (self.rate_on_arrival - self.rate) / max(1e-6, self.rate))
        return 0.5 + 0.35 * placed + 0.15 * gentle

    def says(self) -> str:
        if self.arrived:
            return (f"down in {self.arrived_at:.0f} s, {self.off_the_mark:.1f} m "
                    f"off the mark")
        if self.altitude is not None and self.altitude_now is not None:
            return f"{self.altitude_now:.1f} m off the bottom"
        return f"{self.depth_now:.1f} m down"

    def detail(self) -> dict:
        blind = None
        if self.began_depth is not None and self.locked_at_depth is not None:
            blind = round(self.locked_at_depth - self.began_depth, 2)
        return {
            "arrived": self.arrived,
            "toAltitudeM": self.altitude, "toDepthM": self.depth,
            "altitudeM": None if self.altitude_now is None else round(self.altitude_now, 2),
            "depthM": round(self.depth_now, 2),
            "offTheMarkM": round(self.off_the_mark, 2), "withinM": self.within,
            "rateMs": self.rate,
            "worstRateMs": round(self.worst_rate, 3),
            "rateOnArrivalMs": round(self.rate_on_arrival, 3),
            # The part no real vehicle can report about itself.
            "bottomLock": self.was_told,
            "blindThroughM": blind,
            "lockedAtDepthM": None if self.locked_at_depth is None
            else round(self.locked_at_depth, 2),
            "lockedAtAltitudeM": None if self.locked_at_altitude is None
            else round(self.locked_at_altitude, 2),
            "driftedWhileBlindM": None if self.blind_moved is None
            else round(self.blind_moved, 2),
        }

    def geometry(self) -> dict:
        return {"points": [{"x": float(self.mark[0]), "y": float(self.mark[1])}],
                "circle": {"x": float(self.mark[0]), "y": float(self.mark[1]),
                           "radiusM": self.within}}

    def goal(self) -> dict:
        said = {"kind": "descend", "over": [float(self.mark[0]), float(self.mark[1])],
                "withinM": self.within, "rateMs": self.rate}
        if self.altitude is not None:
            said["altitudeM"] = self.altitude
        else:
            said["depthM"] = self.depth
        return said

    def failed(self) -> bool:
        return self.done and not self.arrived


class Return(Task):
    kind = "return"
    name = "Return"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.home_radius = float(objective.get("homeRadiusM", 2.0))
        self.surface = float(objective.get("surfaceDepthM", 0.5))
        self.limit = float(objective.get("timeLimitS", 300.0))
        # Home is where the dive began unless the objective says otherwise —
        # and a return that begins at home is not a return. `awayM` puts home
        # that far astern, which is the situation the task is about: a vehicle
        # at the far end of its work, asked to come back.
        self.home_at = self.somewhere(objective.get("home"), fallback=self.began_at)
        away = float(objective.get("awayM", 0.0))
        if away > 0:
            ahead = np.array(self.ahead())
            self.home_at = self.home_at.copy()
            self.home_at[:2] = self.began_at[:2] - ahead * away
        self.home = False
        self.surfaced = False
        self.distance = 0.0
        self.depth = 0.0
        self.farthest = 0.0
        # The ascent, reported and not scored. Coming up is the descent's
        # mirror and the half nobody writes down: an untethered vehicle
        # cannot hold station while it rises, so the water takes it, and
        # where it breaks the surface decides whether the boat has to go
        # looking. None of that changes what a return is worth — getting
        # home and surfacing is the job — but a dive that does not say it
        # is a dive whose recovery nobody can plan.
        self.deepest = 0.0
        self.rose_from: np.ndarray | None = None
        self.worst_rate = 0.0
        self.surfaced_off: float | None = None
        self.drifted_up: float | None = None
        self.last: np.ndarray | None = None
        self.last_t: float | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        self.distance = float(np.hypot(*(position[:2] - self.home_at[:2])))
        self.depth = float(-position[2])
        self.farthest = max(self.farthest, self.distance)
        # The deepest it got on this leg is where the ascent began, which is
        # the honest answer on a dive that worked its way up rather than
        # stopping and rising.
        if self.depth >= self.deepest:
            self.deepest = self.depth
            self.rose_from = position[:2].copy()
        if self.last is not None and self.last_t is not None and elapsed > self.last_t:
            up = (float(position[2]) - self.last[2]) / (elapsed - self.last_t)
            self.worst_rate = max(self.worst_rate, up)
        self.last = position.copy()
        self.last_t = elapsed
        if self.distance <= self.home_radius:
            self.home = True
        if self.depth <= self.surface and self.surfaced_off is None:
            self.surfaced_off = self.distance
            if self.rose_from is not None:
                self.drifted_up = float(np.linalg.norm(position[:2] - self.rose_from))
        if self.home and self.depth <= self.surface:
            self.surfaced = True
            self.done = True
        if elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        return 0.5 * float(self.home) + 0.5 * float(self.surfaced)

    def says(self) -> str:
        return f"{self.distance:.1f} m from home, {self.depth:.1f} m down"

    def detail(self) -> dict:
        return {"home": self.home, "surfaced": self.surfaced,
                "distanceM": round(self.distance, 2),
                "depthM": round(self.depth, 2), "farthestM": round(self.farthest, 2),
                "timeLimitS": self.limit,
                # The recovery, for whoever has to be there for it.
                "roseFromM": round(self.deepest, 2),
                "worstRateMs": round(self.worst_rate, 3),
                "surfacedOffM": None if self.surfaced_off is None
                else round(self.surfaced_off, 2),
                "driftedWhileRisingM": None if self.drifted_up is None
                else round(self.drifted_up, 2)}

    def geometry(self) -> dict:
        return {"circle": {"x": float(self.home_at[0]), "y": float(self.home_at[1]),
                           "radiusM": self.home_radius}}

    def goal(self) -> dict:
        return {"kind": "go", "to": [float(self.home_at[0]), float(self.home_at[1])],
                "depthM": float(self.surface), "radiusM": self.home_radius}

    def failed(self) -> bool:
        return self.done and not self.surfaced


class Dock(Task):
    """Get onto the station: charge, and hand over what was recorded.

    The hardest thing here and the most real. It is not enough to arrive: the
    vehicle has to arrive slowly, pointing the right way, inside a tolerance
    that is centimetres rather than metres — and coming in fast is a miss even
    if the position was right, because on a real station that is a broken
    vehicle.
    """

    kind = "dock"
    name = "Dock"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.station = self.somewhere(objective.get("dock") or objective.get("station"),
                                      self.out_from_start(float(objective.get("dx", 15.0)),
                                                          float(objective.get("dy", 0.0)),
                                                          objective.get("depthM")))
        said = objective.get("dock") or objective.get("station") or objective
        facing = said.get("headingDeg") if isinstance(said, dict) else None
        self.facing = self.began_heading if facing is None else math.radians(float(facing))
        self.approach = float(objective.get("approachM", 6.0))
        self.tolerance = float(objective.get("toleranceM", 0.4))
        self.heading_tolerance = math.radians(float(objective.get("headingToleranceDeg", 20.0)))
        self.speed_limit = float(objective.get("speedMs", 0.25))
        self.limit = float(objective.get("timeLimitS", 900.0))
        self.away = float("inf")
        self.docked = False
        self.docked_at = 0.0
        self.too_fast = 0
        self.last: np.ndarray | None = None
        self.last_t: float | None = None
        self.speed = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.last is not None and self.last_t is not None and elapsed > self.last_t:
            self.speed = float(np.linalg.norm(position - self.last) / (elapsed - self.last_t))
        self.last, self.last_t = position.copy(), elapsed
        self.away = float(np.linalg.norm(position - self.station))
        aligned = abs(wrap(heading - self.facing)) <= self.heading_tolerance
        if self.away <= self.tolerance and aligned:
            if self.speed <= self.speed_limit:
                self.docked = True
                self.docked_at = elapsed
                self.done = True
            else:
                self.too_fast += 1
        if elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if self.docked:
            return 1.0
        # Credit for getting close and lined up, because a near miss and a
        # vehicle that never left are not the same failure.
        return max(0.0, min(0.6, 0.6 * (1.0 - min(1.0, self.away / max(1e-6, self.approach)))))

    def says(self) -> str:
        if self.docked:
            return f"docked at {self.docked_at:.0f} s"
        return f"{self.away:.2f} m off the station at {self.speed:.2f} m/s"

    def detail(self) -> dict:
        return {"docked": self.docked, "offM": round(self.away, 3), "speedMs": round(self.speed, 3),
                "toleranceM": self.tolerance, "speedLimitMs": self.speed_limit,
                "arrivedTooFast": self.too_fast,
                "headingToleranceDeg": round(math.degrees(self.heading_tolerance), 1)}

    def geometry(self) -> dict:
        gate = self.station[:2] - np.array([math.cos(self.facing), math.sin(self.facing)]) * self.approach
        return {"points": [{"x": float(self.station[0]), "y": float(self.station[1]),
                            "depthM": float(-self.station[2])}],
                "reached": 1 if self.docked else 0,
                "line": [{"x": float(gate[0]), "y": float(gate[1])},
                         {"x": float(self.station[0]), "y": float(self.station[1])}],
                "circle": {"x": float(self.station[0]), "y": float(self.station[1]),
                           "radiusM": self.approach}}

    def goal(self) -> dict:
        return {"kind": "dock", "station": [float(v) for v in self.station],
                "facingDeg": math.degrees(self.facing), "approachM": self.approach,
                "toleranceM": self.tolerance, "speedLimitMs": self.speed_limit}

    def failed(self) -> bool:
        return self.done and not self.docked


class Wait(Task):
    """Stay where you are for a while: charging, or handing over data.

    Trivial on its own and the reason a mission is a sequence: five minutes on
    the station between two pieces of work is a thing that has to be possible
    to say.
    """

    kind = "wait"
    name = "Wait"

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.seconds = float(objective.get("seconds", 300.0))
        self.reason = str(objective.get("reason", "charging"))
        self.drift_limit = float(objective.get("driftM", 1.0))
        self.here: np.ndarray | None = None
        self.drift = 0.0
        self.waited = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.here is None:
            self.here = position.copy()
        self.drift = float(np.linalg.norm(position - self.here))
        self.waited = elapsed
        if elapsed >= self.seconds:
            self.done = True

    def score(self) -> float:
        kept = 1.0 if self.drift <= self.drift_limit else max(0.0, 1.0 - (self.drift - self.drift_limit) / 5.0)
        return min(1.0, self.waited / max(1e-6, self.seconds)) * kept

    def says(self) -> str:
        return f"{self.waited:.0f} of {self.seconds:.0f} s {self.reason}, {self.drift:.2f} m of drift"

    def detail(self) -> dict:
        return {"waitedS": round(self.waited, 1), "askedS": self.seconds,
                "driftM": round(self.drift, 2), "reason": self.reason}

    def goal(self) -> dict:
        return {"kind": "hold", "at": [float(v) for v in self.began_at]}

    def failed(self) -> bool:
        return self.done and self.waited < self.seconds - 1.0
