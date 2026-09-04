"""What a dive is for, evaluated as it runs.

A task is given the dive's objective — a small JSON document the dive was
defined with — and where the vehicle began, and is then told where the vehicle
is on every step. It keeps a score in [0, 1] as it goes, says how far along it
is for the console, and reduces itself to a result at the end: what was
achieved, how closely, how long it took, how much was asked of the thrusters.
A result rather than a pass mark.

Everything is relative to where the dive began unless the objective says
otherwise, because a task defined on a composer before the dive cannot know the
site's coordinates and should not have to: "hold here", "eight metres ahead
and back", "twenty metres along your heading".

The same code scores the SDK's tank, so a controller that scores well on a
laptop scores the same on the platform.
"""

from __future__ import annotations

import math

import numpy as np

KINDS = ("hold-station", "waypoints", "transect", "survey", "reach", "search",
         "treat", "inspect", "revisit", "dock", "wait", "mission", "return")


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Task:
    kind = "task"
    name = "Task"

    def __init__(self, objective: dict, began_at, heading: float) -> None:
        self.objective = objective
        self.began_at = np.array(began_at, dtype=float)
        self.began_heading = float(heading)
        self.started_t: float | None = None
        self.t = 0.0
        self.effort = 0.0
        self.samples = 0
        self.done = False

    # ── what every task shares ───────────────────────────────────────────────

    def step(self, t: float, position, heading: float, floor: float | None, commands) -> None:
        if self.started_t is None:
            self.started_t = t
        self.t = t
        self.samples += 1
        self.effort += float(np.mean(np.abs(np.asarray(commands, dtype=float)))) if len(commands) else 0.0
        if not self.done:
            self.judge(t - self.started_t, np.asarray(position, dtype=float), float(heading), floor)

    def judge(self, elapsed: float, position: np.ndarray, heading: float, floor: float | None) -> None:
        raise NotImplementedError

    def score(self) -> float:
        return 0.0

    def says(self) -> str:
        return ""

    def detail(self) -> dict:
        return {}

    def geometry(self) -> dict:
        """What to draw on the chart: points, a line, a rectangle, in world xy."""
        return {}

    def route(self) -> list[dict]:
        """The path that does this task, in world metres.

        A task that says what it wants and cannot say how to go about it is a
        task nobody can fly without writing a controller first. Every task here
        can hand over a route the platform's own guidance will follow, so
        choosing one on the dive page and pressing Dive does the thing.

        A controller of somebody's own ignores all of this: it is handed the
        objective and the sensors, and the route is the platform showing its
        working, not an instruction.
        """
        return []

    def route_id(self) -> str:
        """Changes when the route changes, so the vehicle can be re-steered."""
        return self.kind

    def failed(self) -> bool:
        """Whether this ended badly. Done and failed are different things."""
        return False

    def elapsed(self) -> float:
        return 0.0 if self.started_t is None else self.t - self.started_t

    def progress(self) -> dict:
        return {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "says": self.says(), "elapsedS": round(self.elapsed(), 1),
                "detail": self.detail()}

    def result(self) -> dict:
        return {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "failed": self.failed(), "seconds": round(self.elapsed(), 1),
                "thrusterEffort": round(self.effort / max(1, self.samples), 3),
                "achieved": self.detail()}

    def describe(self) -> dict:
        return {"kind": self.kind, "name": self.name, "objective": self.objective,
                "geometry": self.geometry()}

    # ── helpers ──────────────────────────────────────────────────────────────

    def ahead(self) -> tuple[float, float]:
        heading = self.objective.get("headingDeg")
        angle = self.began_heading if heading is None else math.radians(float(heading))
        return math.cos(angle), math.sin(angle)

    def start_depth(self) -> float:
        return float(-self.began_at[2])

    def out_from_start(self, dx: float, dy: float, depth=None) -> np.ndarray:
        """A point the objective gave as ahead-and-to-starboard of the start."""
        ahead = self.ahead()
        right = (ahead[1], -ahead[0])
        z = -float(depth) if depth is not None else float(self.began_at[2])
        return np.array([self.began_at[0] + dx * ahead[0] + dy * right[0],
                         self.began_at[1] + dx * ahead[1] + dy * right[1], z])

    def somewhere(self, said, fallback=None) -> np.ndarray | None:
        """A place named either by the world or by the start.

        `{"x": .., "y": .., "depthM": ..}` is a point in the place — where a
        thing planted in the place is. `{"dx": .., "dy": ..}` is relative to
        where this dive began, which is what a composer can say before the
        dive exists.
        """
        if not isinstance(said, dict):
            return None if fallback is None else np.asarray(fallback, dtype=float)
        if said.get("x") is not None and said.get("y") is not None:
            depth = said.get("depthM")
            z = -float(depth) if depth is not None else float(self.began_at[2])
            return np.array([float(said["x"]), float(said["y"]), z])
        if said.get("dx") is not None or said.get("dy") is not None:
            return self.out_from_start(float(said.get("dx", 0.0)), float(said.get("dy", 0.0)),
                                       said.get("depthM"))
        return None if fallback is None else np.asarray(fallback, dtype=float)

    def lawnmower(self, centre: np.ndarray, width: float, height: float,
                  swath: float, altitude=None, depth=None) -> list[dict]:
        """Up and down a rectangle, the way a survey is actually flown.

        The rectangle runs along the dive's heading and out to starboard from
        `centre`, which is its near corner, and the legs are a swath apart —
        so the ground between them is what the camera sees rather than what
        somebody hoped.
        """
        ahead = np.array(self.ahead())
        right = np.array([ahead[1], -ahead[0]])
        legs = max(1, int(math.ceil(height / max(0.5, swath))))
        route = []
        for leg in range(legs + 1):
            across = min(height, leg * swath)
            ends = [0.0, width] if leg % 2 == 0 else [width, 0.0]
            for along in ends:
                point = centre[:2] + ahead * along + right * across
                said = {"x": float(point[0]), "y": float(point[1])}
                if altitude is not None:
                    said["altitudeM"] = float(altitude)
                elif depth is not None:
                    said["depthM"] = float(depth)
                route.append(said)
        return route


class HoldStation(Task):
    kind = "hold-station"
    name = "Hold station"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
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

    def route(self) -> list[dict]:
        return []          # staying put is what the hold is for


class Waypoints(Task):
    kind = "waypoints"
    name = "Waypoints"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
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

    def route(self) -> list[dict]:
        return [{"x": float(p[0]), "y": float(p[1]), "depthM": float(-p[2])} for p in self.points]

    def failed(self) -> bool:
        return self.done and self.reached < len(self.points)


class Transect(Task):
    kind = "transect"
    name = "Transect"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        self.length = float(objective.get("lengthM", 20.0))
        self.altitude = float(objective.get("altitudeM", 2.0))
        self.band = float(objective.get("altitudeBandM", 0.5))
        self.tolerance = math.radians(float(objective.get("headingToleranceDeg", 10.0)))
        self.ahead_xy = np.array(self.ahead())
        self.line_heading = math.atan2(self.ahead_xy[1], self.ahead_xy[0])
        self.along = 0.0
        self.good = 0.0
        self.last_along: float | None = None
        self.altitude_now: float | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        along = float(np.dot(position[:2] - self.began_at[:2], self.ahead_xy))
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

    def geometry(self) -> dict:
        end = self.began_at[:2] + self.ahead_xy * self.length
        return {"line": [{"x": float(self.began_at[0]), "y": float(self.began_at[1])},
                         {"x": float(end[0]), "y": float(end[1])}]}

    def route(self) -> list[dict]:
        end = self.began_at[:2] + self.ahead_xy * self.length
        return [{"x": float(end[0]), "y": float(end[1]), "altitudeM": self.altitude}]


class Survey(Task):
    """Cover a rectangle. What counts as seen is what the camera's footprint
    on the bottom covered at each pose — derived from the poses and the
    camera, not asserted — when the vehicle carries a camera the catalogue
    describes; a fixed swath otherwise."""

    kind = "survey"
    name = "Survey"

    CELL = 0.5

    def __init__(self, objective, began_at, heading, camera: dict | None = None) -> None:
        super().__init__(objective, began_at, heading)
        self.camera = camera
        self.half_angle = footprint_half_angle(camera)
        self.width = float(objective.get("widthM", 20.0))     # along the heading
        self.height = float(objective.get("heightM", 10.0))   # to starboard
        self.altitude = float(objective.get("altitudeM", 2.0))
        self.band = float(objective.get("altitudeBandM", 1.0))
        self.swath = float(objective.get("swathM", 3.0))
        ahead = self.ahead()
        self.u = np.array(ahead)
        self.v = np.array([ahead[1], -ahead[0]])
        self.columns = max(1, int(round(self.width / self.CELL)))
        self.rows = max(1, int(round(self.height / self.CELL)))
        self.seen = np.zeros((self.rows, self.columns), dtype=bool)
        self.altitude_now: float | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        self.altitude_now = None if floor is None else float(position[2] - floor)
        if self.altitude_now is None or abs(self.altitude_now - self.altitude) > self.band:
            return
        rel = position[:2] - self.began_at[:2]
        along = float(np.dot(rel, self.u))
        across = float(np.dot(rel, self.v))
        # The footprint on the bottom from this altitude, when a camera is
        # known; the declared swath when it is not.
        if self.half_angle is not None:
            half = max(0.25, min(10.0, self.altitude_now * math.tan(self.half_angle)))
            self.swath_now = 2.0 * half
        else:
            half = self.swath / 2.0
            self.swath_now = self.swath
        c0 = max(0, int((along - half) / self.CELL))
        c1 = min(self.columns, int((along + half) / self.CELL) + 1)
        r0 = max(0, int((across - half) / self.CELL))
        r1 = min(self.rows, int((across + half) / self.CELL) + 1)
        if c0 < c1 and r0 < r1:
            self.seen[r0:r1, c0:c1] = True
        if self.seen.all() or elapsed >= float(self.objective.get("timeLimitS", 1e9)):
            self.done = True

    def score(self) -> float:
        return float(self.seen.mean())

    def says(self) -> str:
        return f"{self.score() * 100:.0f}% of the rectangle seen"

    def detail(self) -> dict:
        return {"fractionSeen": round(self.score(), 3), "widthM": self.width, "heightM": self.height,
                "altitudeM": self.altitude, "swathM": round(getattr(self, "swath_now", self.swath), 2),
                "swathFrom": "camera footprint" if self.half_angle is not None else "declared"}

    def geometry(self) -> dict:
        corners = []
        for a, b in ((0, 0), (self.width, 0), (self.width, self.height), (0, self.height)):
            p = self.began_at[:2] + self.u * a + self.v * b
            corners.append({"x": float(p[0]), "y": float(p[1])})
        return {"rectangle": corners, "seen": {"rows": self.rows, "columns": self.columns,
                                               "cells": [int(v) for v in np.packbits(self.seen.ravel())]}}

    def route(self) -> list[dict]:
        # A swath apart, from the footprint the camera will actually have at
        # the altitude this survey asked for.
        if self.half_angle is not None:
            swath = 2.0 * max(0.25, self.altitude * math.tan(self.half_angle))
        else:
            swath = self.swath
        return self.lawnmower(self.began_at, self.width, self.height,
                              swath * 0.9, altitude=self.altitude)

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Return(Task):
    kind = "return"
    name = "Return"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        self.home_radius = float(objective.get("homeRadiusM", 2.0))
        self.surface = float(objective.get("surfaceDepthM", 0.5))
        self.limit = float(objective.get("timeLimitS", 300.0))
        self.home = False
        self.surfaced = False
        self.distance = 0.0
        self.depth = 0.0
        self.farthest = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        self.distance = float(np.hypot(*(position[:2] - self.began_at[:2])))
        self.depth = float(-position[2])
        self.farthest = max(self.farthest, self.distance)
        if self.distance <= self.home_radius:
            self.home = True
            if self.depth <= self.surface:
                self.surfaced = True
                self.done = True
        if elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        return 0.5 * float(self.home) + 0.5 * float(self.surfaced)

    def says(self) -> str:
        return f"{self.distance:.1f} m from home, {self.depth:.1f} m down"

    def detail(self) -> dict:
        return {"home": self.home, "surfaced": self.surfaced, "distanceM": round(self.distance, 2),
                "depthM": round(self.depth, 2), "farthestM": round(self.farthest, 2), "timeLimitS": self.limit}

    def geometry(self) -> dict:
        return {"circle": {"x": float(self.began_at[0]), "y": float(self.began_at[1]), "radiusM": self.home_radius}}

    def route(self) -> list[dict]:
        return [{"x": float(self.began_at[0]), "y": float(self.began_at[1]),
                 "depthM": float(self.surface)}]

    def failed(self) -> bool:
        return self.done and not self.surfaced


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

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
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

    def route(self) -> list[dict]:
        return [{"x": float(self.target[0]), "y": float(self.target[1]),
                 "depthM": float(-self.target[2])}]

    def failed(self) -> bool:
        return self.done and not self.arrived


class Search(Task):
    """Find something that is out there, without being told where.

    The vehicle is given an area and not a position. The thing is found when it
    comes into view — close enough for the camera to resolve it and inside the
    camera's cone — or when a controller says it has found it and is right. Both
    count, because a stack that recognises what it sees is doing the task and a
    platform that flies a pattern until the thing is in front of it is doing the
    task too.

    The chart is told the area and never the answer.
    """

    kind = "search"
    name = "Find it"

    def __init__(self, objective, began_at, heading, camera: dict | None = None) -> None:
        super().__init__(objective, began_at, heading)
        self.camera = camera
        self.half_angle = footprint_half_angle(camera) or math.radians(45.0)
        self.width = float(objective.get("widthM", 30.0))
        self.height = float(objective.get("heightM", 20.0))
        self.altitude = float(objective.get("altitudeM", 2.5))
        self.see = float(objective.get("seeM", 6.0))
        self.limit = float(objective.get("timeLimitS", 900.0))
        self.target = self.somewhere(objective.get("target"),
                                     self.out_from_start(self.width * 0.7, self.height * 0.6))
        self.found = False
        self.found_at = 0.0
        self.reported: np.ndarray | None = None
        self.report_error: float | None = None
        self.closest = float("inf")
        self.travelled = 0.0
        self.last: np.ndarray | None = None

    def report(self, where) -> None:
        """A controller saying where it thinks the thing is."""
        self.reported = np.asarray(where, dtype=float)[:3]
        self.report_error = float(np.linalg.norm(self.reported[:2] - self.target[:2]))
        if self.report_error <= max(2.0, self.see / 2.0):
            self.found = True
            self.found_at = self.elapsed()
            self.done = True

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.last is not None:
            self.travelled += float(np.linalg.norm(position - self.last))
        self.last = position.copy()
        flat = self.target[:2] - position[:2]
        away = float(np.hypot(*flat))
        self.closest = min(self.closest, away)
        if not self.found and away <= self.see:
            # In view: close enough, and inside the camera's cone.
            bearing = math.atan2(float(flat[1]), float(flat[0]))
            if abs(wrap(bearing - heading)) <= self.half_angle:
                self.found = True
                self.found_at = elapsed
                self.done = True
        if elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if not self.found:
            return 0.0
        # Found quickly and without covering the whole ocean to do it.
        quickly = max(0.2, 1.0 - self.found_at / max(1.0, self.limit))
        return min(1.0, 0.6 + 0.4 * quickly)

    def says(self) -> str:
        if self.found:
            return f"found after {self.found_at:.0f} s and {self.travelled:.0f} m"
        return f"searching — {self.travelled:.0f} m covered, nearest pass {self.closest:.1f} m"

    def detail(self) -> dict:
        return {"found": self.found, "foundAtS": round(self.found_at, 1),
                "travelledM": round(self.travelled, 1),
                "closestPassM": None if self.closest == float("inf") else round(self.closest, 2),
                "reportErrorM": None if self.report_error is None else round(self.report_error, 2),
                "seeM": self.see, "timeLimitS": self.limit}

    def geometry(self) -> dict:
        # The area, and — only once it has been found — where it was.
        ahead = np.array(self.ahead())
        right = np.array([ahead[1], -ahead[0]])
        corners = []
        for a, b in ((0, 0), (self.width, 0), (self.width, self.height), (0, self.height)):
            p = self.began_at[:2] + ahead * a + right * b
            corners.append({"x": float(p[0]), "y": float(p[1])})
        drawn = {"rectangle": corners}
        if self.found:
            drawn["points"] = [{"x": float(self.target[0]), "y": float(self.target[1]),
                                "depthM": float(-self.target[2])}]
            drawn["reached"] = 1
        return drawn

    def route(self) -> list[dict]:
        swath = 2.0 * max(0.5, self.altitude * math.tan(self.half_angle)) + self.see
        return self.lawnmower(self.began_at, self.width, self.height,
                              max(2.0, swath * 0.8), altitude=self.altitude)

    def failed(self) -> bool:
        return self.done and not self.found


class Treat(Task):
    """Go over every colony in a patch, low enough and slow enough to do
    something about it.

    This is the task the place makes possible: the colonies are the ones the
    survey found, at the positions it found them, so covering them is covering
    real coral and the score is a share of a real population. A colony counts
    as treated when the vehicle passes within reach of it while low enough and
    slow enough for whatever it is carrying to work.
    """

    kind = "treat"
    name = "Treat the coral"

    def __init__(self, objective, began_at, heading, colonies=None) -> None:
        super().__init__(objective, began_at, heading)
        self.radius = float(objective.get("radiusM", 12.0))
        self.reach = float(objective.get("reachM", 1.2))
        self.altitude = float(objective.get("altitudeM", 1.5))
        self.altitude_band = float(objective.get("altitudeBandM", 1.0))
        self.speed_limit = float(objective.get("speedMs", 0.35))
        self.limit = float(objective.get("timeLimitS", 1800.0))
        centre = self.somewhere(objective.get("centre"), self.began_at)
        self.centre = np.asarray(centre, dtype=float)
        near = []
        for colony in (colonies or []):
            if float(np.hypot(colony[0] - self.centre[0], colony[1] - self.centre[1])) <= self.radius:
                near.append([float(colony[0]), float(colony[1])])
        self.colonies = np.array(near, dtype=float) if near else np.zeros((0, 2))
        self.treated = np.zeros(len(self.colonies), dtype=bool)
        self.altitude_now: float | None = None
        self.passes = 0
        self.last: np.ndarray | None = None
        self.travelled = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.last is not None:
            self.travelled += float(np.linalg.norm(position - self.last))
        self.last = position.copy()
        self.altitude_now = None if floor is None else float(position[2] - floor)
        low = self.altitude_now is not None and self.altitude_now <= self.altitude + self.altitude_band
        if low and len(self.colonies):
            away = np.hypot(self.colonies[:, 0] - position[0], self.colonies[:, 1] - position[1])
            fresh = (away <= self.reach) & ~self.treated
            if fresh.any():
                self.treated |= fresh
                self.passes += int(fresh.sum())
        if (len(self.colonies) and self.treated.all()) or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if not len(self.colonies):
            return 0.0
        return float(self.treated.mean())

    def says(self) -> str:
        if not len(self.colonies):
            return "no colonies in this patch"
        return f"{int(self.treated.sum())} of {len(self.colonies)} colonies treated"

    def detail(self) -> dict:
        return {"treated": int(self.treated.sum()), "of": int(len(self.colonies)),
                "radiusM": self.radius, "reachM": self.reach, "altitudeM": self.altitude,
                "speedLimitMs": self.speed_limit, "travelledM": round(self.travelled, 1)}

    def geometry(self) -> dict:
        drawn = {"circle": {"x": float(self.centre[0]), "y": float(self.centre[1]),
                            "radiusM": self.radius}}
        if len(self.colonies):
            drawn["marks"] = [{"x": float(c[0]), "y": float(c[1]), "done": bool(d)}
                              for c, d in zip(self.colonies[:400], self.treated[:400])]
        return drawn

    def route(self) -> list[dict]:
        corner = self.centre.copy()
        ahead = np.array(self.ahead())
        right = np.array([ahead[1], -ahead[0]])
        corner[:2] = self.centre[:2] - ahead * self.radius - right * self.radius
        return self.lawnmower(corner, 2.0 * self.radius, 2.0 * self.radius,
                              max(1.0, self.reach * 1.6), altitude=self.altitude)

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Inspect(Task):
    """Go round a thing, keeping it in frame from a fixed distance.

    Scored on how much of the way round was actually seen: the circle is cut
    into sectors, and a sector counts when the vehicle was in it, at about the
    right distance, with the thing in front of it. Which is what an inspection
    is — not a lap, a look at every side.
    """

    kind = "inspect"
    name = "Inspect"

    SECTORS = 12

    def __init__(self, objective, began_at, heading, camera: dict | None = None) -> None:
        super().__init__(objective, began_at, heading)
        self.half_angle = footprint_half_angle(camera) or math.radians(45.0)
        self.radius = float(objective.get("radiusM", 4.0))
        self.band = float(objective.get("bandM", 2.0))
        self.limit = float(objective.get("timeLimitS", 900.0))
        self.target = self.somewhere(objective.get("target"),
                                     self.out_from_start(float(objective.get("dx", 10.0)),
                                                         float(objective.get("dy", 0.0)),
                                                         objective.get("depthM")))
        self.seen = np.zeros(self.SECTORS, dtype=bool)
        self.away = 0.0

    def judge(self, elapsed, position, heading, floor) -> None:
        flat = position[:2] - self.target[:2]
        self.away = float(np.hypot(*flat))
        if abs(self.away - self.radius) <= self.band:
            towards = math.atan2(-float(flat[1]), -float(flat[0]))
            if abs(wrap(towards - heading)) <= self.half_angle:
                where = math.atan2(float(flat[1]), float(flat[0]))
                sector = int(((where + math.pi) / (2 * math.pi)) * self.SECTORS) % self.SECTORS
                self.seen[sector] = True
        if self.seen.all() or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        return float(self.seen.mean())

    def says(self) -> str:
        return f"{int(self.seen.sum())} of {self.SECTORS} sides seen, {self.away:.1f} m off it"

    def detail(self) -> dict:
        return {"sidesSeen": int(self.seen.sum()), "of": self.SECTORS,
                "radiusM": self.radius, "bandM": self.band, "offM": round(self.away, 2)}

    def geometry(self) -> dict:
        return {"circle": {"x": float(self.target[0]), "y": float(self.target[1]),
                           "radiusM": self.radius},
                "points": [{"x": float(self.target[0]), "y": float(self.target[1]),
                            "depthM": float(-self.target[2])}]}

    def route(self) -> list[dict]:
        # Round it, facing it the whole way: an inspection that looks where it
        # is going has its back to the thing it came to look at, which is how
        # a lap of a structure sees one side of it.
        looking = {"x": float(self.target[0]), "y": float(self.target[1])}
        route = []
        for sector in range(self.SECTORS * 2 + 1):
            angle = math.pi * sector / self.SECTORS
            route.append({"x": float(self.target[0] + self.radius * math.cos(angle)),
                          "y": float(self.target[1] + self.radius * math.sin(angle)),
                          "depthM": float(-self.target[2]),
                          "facing": looking, "arriveM": max(0.4, self.radius * 0.2)})
        return route

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Revisit(Task):
    """Visit each of a list of marked colonies and hold there long enough to
    sample. The survey a reef monitoring programme actually runs."""

    kind = "revisit"
    name = "Revisit"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        self.reach = float(objective.get("reachM", 1.0))
        self.hold_for = float(objective.get("holdS", 10.0))
        self.limit = float(objective.get("timeLimitS", 1200.0))
        self.marks = [self.somewhere(one, self.out_from_start(0.0, 0.0))
                      for one in objective.get("marks", [{"dx": 8, "dy": 0}, {"dx": 16, "dy": 6}])]
        self.held = [0.0 for _ in self.marks]
        self.last_t: float | None = None
        self.at: int | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        dt = 0.0 if self.last_t is None else elapsed - self.last_t
        self.last_t = elapsed
        self.at = None
        for i, mark in enumerate(self.marks):
            if float(np.hypot(*(position[:2] - mark[:2]))) <= self.reach:
                self.held[i] += dt
                self.at = i
                break
        if all(h >= self.hold_for for h in self.held) or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        if not self.marks:
            return 0.0
        return float(np.mean([min(1.0, h / max(1e-6, self.hold_for)) for h in self.held]))

    def says(self) -> str:
        done = sum(1 for h in self.held if h >= self.hold_for)
        where = "" if self.at is None else f", sampling {self.at + 1}"
        return f"{done} of {len(self.marks)} sampled{where}"

    def detail(self) -> dict:
        return {"sampled": sum(1 for h in self.held if h >= self.hold_for), "of": len(self.marks),
                "heldS": [round(h, 1) for h in self.held], "holdS": self.hold_for,
                "reachM": self.reach}

    def geometry(self) -> dict:
        return {"points": [{"x": float(m[0]), "y": float(m[1]), "depthM": float(-m[2])}
                           for m in self.marks],
                "reached": sum(1 for h in self.held if h >= self.hold_for)}

    def route(self) -> list[dict]:
        # Held at, not merely passed over: the sample is the ten seconds.
        return [{"x": float(m[0]), "y": float(m[1]), "depthM": float(-m[2]),
                 "arriveM": max(0.25, self.reach * 0.6), "holdS": self.hold_for + 1.0}
                for m in self.marks]

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


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

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
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

    def route(self) -> list[dict]:
        # The gate first, on the station's own heading, then straight in. A
        # vehicle that arrives from the side arrives across the cradle.
        into = np.array([math.cos(self.facing), math.sin(self.facing)])
        gate = self.station[:2] - into * self.approach
        return [
            {"x": float(gate[0]), "y": float(gate[1]), "depthM": float(-self.station[2]),
             "arriveM": max(0.5, self.approach * 0.15)},
            # Onto the cradle: inside half the tolerance, and slower than the
            # station will accept, because arriving fast is a miss.
            {"x": float(self.station[0]), "y": float(self.station[1]),
             "depthM": float(-self.station[2]),
             "arriveM": max(0.08, self.tolerance * 0.5),
             "speedMs": max(0.05, self.speed_limit * 0.5),
             "easeM": max(1.0, self.approach * 0.6)},
        ]

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

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
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

    def route(self) -> list[dict]:
        return []

    def failed(self) -> bool:
        return self.done and self.waited < self.seconds - 1.0


class Mission(Task):
    """Several things, in order, as one dive.

    A dive stopped being one objective here. Each stage is a task in its own
    right, scored on its own terms and reported on its own line; the mission is
    over when the last one finishes or when one of them fails, because a
    mission that carries on after a failed dock is a mission pretending.
    """

    kind = "mission"
    name = "Mission"

    def __init__(self, objective, began_at, heading, make) -> None:
        super().__init__(objective, began_at, heading)
        self.make = make
        self.stages: list[Task] = []
        for stage in objective.get("stages", []):
            made = make(stage, began_at, heading)
            if made is not None:
                self.stages.append(made)
        self.at = 0
        self.finished: list[dict] = []
        self.stopped_early = False

    @property
    def stage(self) -> Task | None:
        return self.stages[self.at] if self.at < len(self.stages) else None

    def step(self, t, position, heading, floor, commands) -> None:
        # The mission's own clock runs; the stage's clock starts when it does.
        if self.started_t is None:
            self.started_t = t
        self.t = t
        self.samples += 1
        self.effort += float(np.mean(np.abs(np.asarray(commands, dtype=float)))) if len(commands) else 0.0
        stage = self.stage
        if stage is None or self.done:
            self.done = True
            return
        stage.step(t, position, heading, floor, commands)
        if stage.done:
            self.finished.append(stage.result())
            if stage.failed():
                self.stopped_early = True
                self.done = True
                return
            self.at += 1
            if self.stage is None:
                self.done = True

    def judge(self, elapsed, position, heading, floor) -> None:      # pragma: no cover
        pass

    def score(self) -> float:
        scores = [one["score"] for one in self.finished]
        stage = self.stage
        if stage is not None and not self.done:
            scores.append(stage.score())
        if not self.stages:
            return 0.0
        # Stages never reached count as nothing, which is what they are.
        return float(sum(scores) / len(self.stages))

    def says(self) -> str:
        stage = self.stage
        where = f"{min(self.at + 1, len(self.stages))} of {len(self.stages)}"
        if stage is None:
            return f"all {len(self.stages)} stages done"
        return f"stage {where}: {stage.name} — {stage.says()}"

    def detail(self) -> dict:
        stage = self.stage
        return {"stage": self.at, "of": len(self.stages),
                "stageName": None if stage is None else stage.name,
                "stopped": self.stopped_early,
                "stages": self.finished + ([stage.progress()] if stage is not None else [])}

    def geometry(self) -> dict:
        stage = self.stage
        return {} if stage is None else stage.geometry()

    def route(self) -> list[dict]:
        stage = self.stage
        return [] if stage is None else stage.route()

    def route_id(self) -> str:
        return f"mission:{self.at}"

    def describe(self) -> dict:
        said = super().describe()
        said["stages"] = [{"kind": s.kind, "name": s.name} for s in self.stages]
        return said

    def failed(self) -> bool:
        return self.stopped_early or any(one.get("failed") for one in self.finished)


class Unavailable(Task):
    """A task the platform knows of and cannot yet judge here."""

    kind = "inspect"
    name = "Inspect"

    def __init__(self, objective, began_at, heading, why: str) -> None:
        super().__init__(objective, began_at, heading)
        self.why = why
        self.done = True

    def judge(self, elapsed, position, heading, floor) -> None:
        pass

    def says(self) -> str:
        return self.why

    def detail(self) -> dict:
        return {"unavailable": self.why}


TASKS = {"hold-station": HoldStation, "waypoints": Waypoints, "transect": Transect,
         "survey": Survey, "return": Return, "reach": Reach, "search": Search,
         "treat": Treat, "inspect": Inspect, "revisit": Revisit, "dock": Dock,
         "wait": Wait}


def footprint_half_angle(camera: dict | None) -> float | None:
    """Half the camera's horizontal field of view, in radians, or None.

    From the catalogue's field of view where it states one, else from the
    focal length as a 36 mm-equivalent — which is what a focal length on its
    own means to anybody reading it.
    """
    if not camera:
        return None
    fov = camera.get("horizontalFovDeg")
    if fov:
        return math.radians(float(fov)) / 2.0
    focal = camera.get("focalLengthMm")
    if focal:
        return math.atan(18.0 / float(focal))
    return None


def task_for(objective, began_at, heading: float, camera: dict | None = None,
             colonies=None) -> Task | None:
    """The task an objective asks for, or None when the dive is only flown.

    `colonies` is where the coral actually is, for the tasks that are about
    coral. A task that needs it and is not given it says so in its score rather
    than inventing a population.
    """
    if not isinstance(objective, dict) or not objective:
        return None
    kind = str(objective.get("kind", ""))
    if kind == "mission":
        def stage(said, began, heading_):
            return task_for(said, began, heading_, camera=camera, colonies=colonies)
        return Mission(objective, began_at, heading, stage)
    made = TASKS.get(kind)
    if made is None:
        return None
    if made is Survey:
        return Survey(objective, began_at, heading, camera=camera)
    if made is Search:
        return Search(objective, began_at, heading, camera=camera)
    if made is Inspect:
        return Inspect(objective, began_at, heading, camera=camera)
    if made is Treat:
        return Treat(objective, began_at, heading, colonies=colonies)
    return made(objective, began_at, heading)
