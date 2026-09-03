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

KINDS = ("hold-station", "waypoints", "transect", "survey", "inspect", "return")


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

    def elapsed(self) -> float:
        return 0.0 if self.started_t is None else self.t - self.started_t

    def progress(self) -> dict:
        return {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "says": self.says(), "elapsedS": round(self.elapsed(), 1),
                "detail": self.detail()}

    def result(self) -> dict:
        return {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "seconds": round(self.elapsed(), 1),
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
         "survey": Survey, "return": Return}


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


def task_for(objective, began_at, heading: float, camera: dict | None = None) -> Task | None:
    """The task an objective asks for, or None when the dive is only flown."""
    if not isinstance(objective, dict) or not objective:
        return None
    kind = str(objective.get("kind", ""))
    if kind == "inspect":
        return Unavailable(objective, began_at, heading, "needs a structure in the place to circle; none is placed yet")
    made = TASKS.get(kind)
    if made is None:
        return None
    if made is Survey:
        return Survey(objective, began_at, heading, camera=camera)
    return made(objective, began_at, heading)
