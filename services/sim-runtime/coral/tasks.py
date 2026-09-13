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
         "treat", "outplant", "monitor", "profile", "section", "inspect", "revisit", "dock", "wait", "mission", "return")


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Task:
    kind = "task"
    name = "Task"
    # Whether this asks the vehicle to stop. Most tasks do somewhere — arrive,
    # hold, work, dock — and a vehicle that cannot stop cannot be asked. A
    # glider is the reason the question exists: it does not hover badly, it
    # falls out of the water column, and a dive that lets it try is a dive
    # that has wasted somebody's day proving something arithmetic.
    needs_hover = True

    def __init__(self, objective: dict, began_at, heading: float) -> None:
        self.objective = objective
        self.began_at = np.array(began_at, dtype=float)
        self.began_heading = float(heading)
        self.started_t: float | None = None
        self.t = 0.0
        self.effort = 0.0
        self.samples = 0
        self.done = False
        self.believed: np.ndarray | None = None

    # ── what every task shares ───────────────────────────────────────────────

    def step(self, t: float, position, heading: float, floor: float | None, commands,
             believed=None) -> None:
        if self.started_t is None:
            self.started_t = t
        self.t = t
        self.samples += 1
        self.effort += float(np.mean(np.abs(np.asarray(commands, dtype=float)))) if len(commands) else 0.0
        # Where the vehicle thinks it is, for the few tasks that need to know.
        # Kept on the task rather than added to every `judge` signature: a task
        # is scored against the truth and that is the rule, but a task that
        # models somebody *doing* something has to know when the vehicle
        # believed it had arrived, because that is when the work happens. The
        # gap between the two is then the finding rather than the error.
        self.believed = None if believed is None else np.asarray(believed, dtype=float)
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

    def goal(self) -> dict:
        """What this task wants, in the world's own coordinates. Not how.

        A task used to carry the route that solved it, and the runtime flew
        that route — so what was being measured was a line we had supplied,
        and no controller was compared to anything. What a task says now is
        the specification: cover this rectangle at this altitude, hold this
        station, come home to this dock. Working out a path that satisfies it
        is a controller's job, and the platform's own planner is one of those
        (controllers/plan.py) rather than a privilege of the task.

        Stated absolutely, never relative to where the vehicle happens to be,
        because that is what a plan is: the same document whether it was
        written by a person, emitted by a model, or worked out here.
        """
        return {}

    def goal_id(self) -> str:
        """Changes when the goal changes, so a controller can be told again."""
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

    def goal(self) -> dict:
        return {"kind": "hold", "at": [float(v) for v in self.began_at],
                "radiusM": self.radius}


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

    def goal(self) -> dict:
        return {"kind": "visit", "points": [[float(v) for v in p] for p in self.points],
                "radiusM": self.radius}

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

    def goal(self) -> dict:
        end = self.began_at[:2] + self.ahead_xy * self.length
        return {"kind": "line", "from": [float(v) for v in self.began_at[:2]],
                "to": [float(end[0]), float(end[1])], "altitudeM": self.altitude}


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

    def goal(self) -> dict:
        # The rectangle, said in the world rather than as "ahead of where you
        # started": a corner, a direction along it, and two lengths. How far
        # apart to fly the lanes is not stated, because that depends on what
        # the vehicle can see and is therefore the controller's business.
        return {"kind": "cover", "corner": [float(v) for v in self.began_at[:2]],
                "along": [float(v) for v in self.u[:2]],
                "widthM": self.width, "heightM": self.height,
                "altitudeM": self.altitude, "swathM": self.swath}

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

    def judge(self, elapsed, position, heading, floor) -> None:
        self.distance = float(np.hypot(*(position[:2] - self.home_at[:2])))
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
        return {"circle": {"x": float(self.home_at[0]), "y": float(self.home_at[1]),
                           "radiusM": self.home_radius}}

    def goal(self) -> dict:
        return {"kind": "go", "to": [float(self.home_at[0]), float(self.home_at[1])],
                "depthM": float(self.surface), "radiusM": self.home_radius}

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

    def goal(self) -> dict:
        return {"kind": "go", "to": [float(v) for v in self.target], "radiusM": self.radius}

    def failed(self) -> bool:
        return self.done and not self.arrived


class Search(Task):
    """Find something that is out there, without being told where.

    The vehicle is given an area and not a position. The thing is found when it
    passes through the camera's footprint on the bottom — or when a controller
    says it has found it and is right. Both count, because a stack that
    recognises what it sees is doing the task, and a platform that flies a
    pattern until the thing goes under it is doing the task too.

    Under it, not in front of it. This was written as a forward cone, and the
    result was a search that only succeeded when the navigation was bad: a
    vehicle flying tidy lanes passes its target abeam, which a cone in front
    never sees, while one wandering by twenty metres eventually points at it.
    A survey camera looks down. What it sees is a swath under the vehicle as
    wide as the altitude and the lens make it, and how far you can see through
    the water decides whether it sees the bottom at all.

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
        swath = self.swath_at(position, floor)
        if not self.found and swath > 0.0 and away <= swath:
            self.found = True
            self.found_at = elapsed
            self.done = True
        if elapsed >= self.limit:
            self.done = True

    def swath_at(self, position, floor) -> float:
        """How far to either side the camera is seeing the bottom, right now.

        Two things decide it and both are real: the lens and the height it is
        flown at give the footprint, and the water decides whether the bottom
        is visible at all. Fly too high for the visibility and the camera is
        looking at green.
        """
        altitude = None if floor is None else float(position[2]) - float(floor)
        if altitude is None:
            altitude = self.altitude
        if altitude > self.see:
            return 0.0                      # too high to see the bottom in this water
        return max(0.25, altitude * math.tan(self.half_angle))

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

    def goal(self) -> dict:
        ahead = np.array(self.ahead())
        return {"kind": "cover", "corner": [float(v) for v in self.began_at[:2]],
                "along": [float(ahead[0]), float(ahead[1])],
                "widthM": self.width, "heightM": self.height,
                "altitudeM": self.altitude, "seeM": self.see}

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
                "speedLimitMs": self.speed_limit, "travelledM": round(self.travelled, 1),
                # Which ones, not just how many. The recording's geometry keeps
                # the colonies and their state at the end of the dive, so a
                # replay drawing from it shows every colony treated from the
                # first frame — the one thing a treatment replay is for is
                # watching them go green in the order they were worked.
                # A bit each, eight to a byte: a hundred and twenty colonies
                # is sixteen bytes a second.
                "doneBits": [int(v) for v in np.packbits(self.treated[:400])]}

    def geometry(self) -> dict:
        drawn = {"circle": {"x": float(self.centre[0]), "y": float(self.centre[1]),
                            "radiusM": self.radius}}
        if len(self.colonies):
            drawn["marks"] = [{"x": float(c[0]), "y": float(c[1]), "done": bool(d)}
                              for c, d in zip(self.colonies[:400], self.treated[:400])]
        return drawn

    def goal(self) -> dict:
        ahead = np.array(self.ahead())
        return {"kind": "work", "centre": [float(v) for v in self.centre],
                "along": [float(ahead[0]), float(ahead[1])],
                "radiusM": self.radius, "reachM": self.reach, "altitudeM": self.altitude}

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Outplant(Task):
    """Plant corals where the plan said, and find out where they actually went.

    The work KAUST is doing at Shushah Island is two million corals into the
    seabed by 2030, a hundred hectares cut into grids, and every one of them is
    meant to go somewhere in particular — nurseries are stocked by species and
    genotype, and a restoration that cannot say where it put things is a
    restoration nobody can come back and measure.

    Which makes this the task that asks the platform's own question hardest.
    The vehicle plants where it *believes* the mark is; the coral ends up where
    the vehicle *actually* is. Nothing about the planting fails when navigation
    is bad — the manipulator works perfectly, the coral goes in, the log says
    done — and the colony is five metres from where the plan wanted it. On an
    array you plant on the mark. On dead reckoning you plant a reef nobody can
    find again, and the only way to know is to measure the truth against the
    belief, which is the one thing a real vehicle cannot do and this can.

    So the score is not how many were planted. It is how many were planted
    where they were meant to go.
    """

    kind = "outplant"
    name = "Outplant coral"

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        # How close the vehicle has to believe it is before it plants, how low
        # and how slow — a manipulator needs the vehicle still — and how long
        # it has to stay there to get the coral in the ground.
        self.place = float(objective.get("placeM", 0.5))
        self.altitude = float(objective.get("altitudeM", 1.0))
        self.band = float(objective.get("altitudeBandM", 0.5))
        self.speed_limit = float(objective.get("speedMs", 0.2))
        self.hold = float(objective.get("holdS", 5.0))
        # How far from its mark a coral may land and still count. Wider than
        # `placeM` on purpose: one is what the vehicle is trying to do, the
        # other is what the programme will accept.
        self.tolerance = float(objective.get("toleranceM", 1.0))
        self.limit = float(objective.get("timeLimitS", 1800.0))

        self.marks: list[np.ndarray] = []
        for said in objective.get("positions", []) or []:
            where = self.somewhere(said)
            if where is not None:
                self.marks.append(where)
        cell = objective.get("cell")
        if not self.marks and isinstance(cell, dict):
            self.marks = self._grid(cell)
        self.marks = self.marks[:400]

        self.at = 0
        self.planted_at: list[np.ndarray] = []       # where each one actually went
        self.errors: list[float] = []                # and how far that was from its mark
        self.since: float | None = None
        self.last: np.ndarray | None = None
        self.last_t: float | None = None
        self.speed = 0.0
        self.altitude_now: float | None = None

    def _grid(self, cell: dict) -> list[np.ndarray]:
        """Planting positions laid out over a cell, the way a grid is worked.

        A restoration does not plant at scattered points; it works a cell in
        rows at a stated spacing, because that is what can be checked off and
        come back to.
        """
        width = float(cell.get("widthM", 10.0))
        height = float(cell.get("heightM", 10.0))
        spacing = max(0.25, float(cell.get("spacingM", 2.0)))
        marks = []
        rows = max(1, int(height // spacing) + 1)
        columns = max(1, int(width // spacing) + 1)
        for row in range(rows):
            across = range(columns) if row % 2 == 0 else reversed(range(columns))
            for column in across:
                marks.append(self.out_from_start(column * spacing, row * spacing))
        return marks

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.last is not None and self.last_t is not None and elapsed > self.last_t:
            self.speed = float(np.linalg.norm(position - self.last) / (elapsed - self.last_t))
        self.last, self.last_t = position.copy(), elapsed
        self.altitude_now = None if floor is None else float(position[2] - floor)

        if self.at >= len(self.marks) or elapsed >= self.limit:
            self.done = True
            return

        mark = self.marks[self.at]
        # Against belief, because this is the vehicle deciding it has arrived.
        # It has no other way to decide, and neither does a real one.
        here = position if self.believed is None else self.believed
        near = float(np.hypot(here[0] - mark[0], here[1] - mark[1])) <= self.place
        low = (self.altitude_now is not None
               and self.altitude_now <= self.altitude + self.band)
        still = self.speed <= self.speed_limit
        if not (near and low and still):
            self.since = None
            return
        if self.since is None:
            self.since = float(elapsed)
        if elapsed - self.since < self.hold:
            return
        # In the ground. Where it is, is where the vehicle is — not where the
        # vehicle thought it was, and not where the plan asked for.
        self.planted_at.append(position[:2].copy())
        self.errors.append(float(np.hypot(position[0] - mark[0], position[1] - mark[1])))
        self.at += 1
        self.since = None
        if self.at >= len(self.marks):
            self.done = True

    def on_the_mark(self) -> int:
        return int(sum(1 for e in self.errors if e <= self.tolerance))

    def score(self) -> float:
        if not self.marks:
            return 0.0
        return float(self.on_the_mark()) / float(len(self.marks))

    def says(self) -> str:
        if not self.marks:
            return "nowhere to plant"
        if not self.errors:
            return f"0 of {len(self.marks)} planted"
        return (f"{len(self.errors)} of {len(self.marks)} planted, "
                f"{self.on_the_mark()} on the mark, "
                f"{float(np.mean(self.errors)):.2f} m out on average")

    def detail(self) -> dict:
        return {
            "planted": len(self.errors),
            "of": len(self.marks),
            "onTheMark": self.on_the_mark(),
            "toleranceM": self.tolerance,
            "placeM": self.place,
            "meanErrorM": round(float(np.mean(self.errors)), 3) if self.errors else None,
            "worstErrorM": round(float(max(self.errors)), 3) if self.errors else None,
            # Where every coral actually went. The point of keeping it is that
            # a restoration has to be able to go back and find what it planted,
            # and this is the only record of the difference between the map and
            # the reef.
            "wentTo": [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in self.planted_at],
        }

    def geometry(self) -> dict:
        drawn = {"marks": [{"x": float(m[0]), "y": float(m[1]), "done": i < len(self.errors)}
                           for i, m in enumerate(self.marks)]}
        if self.planted_at:
            drawn["planted"] = [{"x": float(p[0]), "y": float(p[1])} for p in self.planted_at]
        return drawn

    def goal(self) -> dict:
        return {"kind": "visit",
                "points": [[float(v) for v in m] for m in self.marks],
                "radiusM": self.place, "holdS": self.hold, "altitudeM": self.altitude}

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Monitor(Task):
    """Work a grid cell to a standard something can be reconstructed from.

    A survey scores the ground it passed over. That is the wrong question for
    a monitoring programme, because a run that covers every square metre from
    the wrong height, or too fast for the shutter, produces imagery no
    photogrammetry will close — and scores full marks for it. The hundred
    hectares at Shushah Island are monitored so that a model can be built and
    compared against last year's; coverage that cannot be reconstructed is a
    dive that has to be flown again.

    So a cell counts when it was imaged *usefully*: from inside a tight
    altitude band, because altitude is scale and scale drifting through a
    mosaic is what tears it; and slowly enough not to smear. Both are held
    against the truth, and both are things a vehicle fighting a current stops
    being able to do long before it stops covering ground.

    What it comes back with is a finding rather than a percentage: how much of
    the cell is usable, and how many colonies were under the camera while it
    was.
    """

    kind = "monitor"
    name = "Monitor a grid cell"

    CELL = 0.5

    def __init__(self, objective, began_at, heading, camera: dict | None = None,
                 colonies=None) -> None:
        super().__init__(objective, began_at, heading)
        self.camera = camera
        self.half_angle = footprint_half_angle(camera)
        cell = objective.get("cell") or {}
        self.width = float(objective.get("widthM", cell.get("widthM", 25.0)))
        self.height = float(objective.get("heightM", cell.get("heightM", 25.0)))
        self.name_of_cell = str(cell.get("name", "") or objective.get("cellName", ""))
        self.altitude = float(objective.get("altitudeM", 4.0))
        # Tighter than a survey's on purpose. A survey wants to have been over
        # the ground; this wants every frame at the same scale.
        self.band = float(objective.get("altitudeBandM", 0.5))
        self.speed_limit = float(objective.get("speedMs", 0.3))
        self.swath = float(objective.get("swathM", 3.0))
        self.limit = float(objective.get("timeLimitS", 1800.0))

        ahead = self.ahead()
        self.u = np.array(ahead)
        self.v = np.array([ahead[1], -ahead[0]])
        self.columns = max(1, int(round(self.width / self.CELL)))
        self.rows = max(1, int(round(self.height / self.CELL)))
        self.seen = np.zeros((self.rows, self.columns), dtype=bool)     # passed over
        self.usable = np.zeros((self.rows, self.columns), dtype=bool)   # and worth having

        near = []
        for colony in (colonies or []):
            rel = np.array([float(colony[0]), float(colony[1])]) - self.began_at[:2]
            along, across = float(np.dot(rel, self.u)), float(np.dot(rel, self.v))
            if 0.0 <= along <= self.width and 0.0 <= across <= self.height:
                near.append([along, across])
        self.colonies = np.array(near, dtype=float) if near else np.zeros((0, 2))
        self.imaged = np.zeros(len(self.colonies), dtype=bool)

        self.altitude_now: float | None = None
        self.speed = 0.0
        self.too_high = 0
        self.too_fast = 0
        self.last: np.ndarray | None = None
        self.last_t: float | None = None
        self.swath_now = self.swath

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.last is not None and self.last_t is not None and elapsed > self.last_t:
            self.speed = float(np.linalg.norm(position - self.last) / (elapsed - self.last_t))
        self.last, self.last_t = position.copy(), elapsed
        self.altitude_now = None if floor is None else float(position[2] - floor)
        if elapsed >= self.limit or self.usable.all():
            self.done = True
            return
        if self.altitude_now is None:
            return

        if self.half_angle is not None:
            half = max(0.25, min(10.0, self.altitude_now * math.tan(self.half_angle)))
            self.swath_now = 2.0 * half
        else:
            half = self.swath / 2.0

        rel = position[:2] - self.began_at[:2]
        along = float(np.dot(rel, self.u))
        across = float(np.dot(rel, self.v))
        c0 = max(0, int((along - half) / self.CELL))
        c1 = min(self.columns, int((along + half) / self.CELL) + 1)
        r0 = max(0, int((across - half) / self.CELL))
        r1 = min(self.rows, int((across + half) / self.CELL) + 1)
        if not (c0 < c1 and r0 < r1):
            return
        self.seen[r0:r1, c0:c1] = True

        # Counted once each, on the step it first goes wrong, so the numbers
        # say how much of the dive was spent unusable rather than how many
        # physics steps it took.
        high = abs(self.altitude_now - self.altitude) > self.band
        fast = self.speed > self.speed_limit
        if high or fast:
            self.too_high += 1 if high else 0
            self.too_fast += 1 if fast else 0
            return
        self.usable[r0:r1, c0:c1] = True
        if len(self.colonies):
            under = ((np.abs(self.colonies[:, 0] - along) <= half)
                     & (np.abs(self.colonies[:, 1] - across) <= half))
            self.imaged |= under

    def score(self) -> float:
        return float(self.usable.mean())

    def says(self) -> str:
        covered, good = self.seen.mean(), self.usable.mean()
        if covered <= 0.0:
            return "nothing of the cell yet"
        return (f"{good * 100:.0f}% usable of {covered * 100:.0f}% covered, "
                f"{int(self.imaged.sum())} of {len(self.colonies)} colonies imaged")

    def detail(self) -> dict:
        return {"cell": self.name_of_cell or None,
                "widthM": self.width, "heightM": self.height,
                "fractionSeen": round(float(self.seen.mean()), 3),
                "fractionUsable": round(float(self.usable.mean()), 3),
                "altitudeM": self.altitude, "altitudeBandM": self.band,
                "speedLimitMs": self.speed_limit,
                "swathM": round(self.swath_now, 2),
                "swathFrom": "camera footprint" if self.half_angle is not None else "declared",
                # Why the unusable part was unusable. A cell that came back at
                # forty per cent is a different problem depending on which of
                # these is large, and re-flying it blind is how a programme
                # wastes a season.
                "stepsTooHigh": self.too_high, "stepsTooFast": self.too_fast,
                "coloniesImaged": int(self.imaged.sum()), "coloniesInCell": int(len(self.colonies)),
                "usableCells": {"rows": self.rows, "columns": self.columns,
                                "cells": [int(v) for v in np.packbits(self.usable.ravel())]}}

    def geometry(self) -> dict:
        corners = []
        for a, b in ((0, 0), (self.width, 0), (self.width, self.height), (0, self.height)):
            point = self.began_at[:2] + self.u * a + self.v * b
            corners.append({"x": float(point[0]), "y": float(point[1])})
        return {"rectangle": corners,
                "seen": {"rows": self.rows, "columns": self.columns,
                         "cells": [int(v) for v in np.packbits(self.usable.ravel())]}}

    def goal(self) -> dict:
        return {"kind": "cover", "corner": [float(v) for v in self.began_at[:2]],
                "along": [float(v) for v in self.u[:2]],
                "widthM": self.width, "heightM": self.height,
                "altitudeM": self.altitude, "swathM": self.swath,
                "speedMs": self.speed_limit}

    def failed(self) -> bool:
        return self.done and self.score() < 0.9


class Profile(Task):
    """Down to a depth and back. The unit a glider mission is built from.

    Everything a buoyancy glider does is made of these: it cannot hold a depth
    and it cannot stop, so the only thing it can be asked for is the shape of
    the sawtooth and how many teeth. What comes back is a column of water
    measured top to bottom, which is what an oceanographer wanted in the first
    place.
    """

    kind = "profile"
    name = "Profile the water column"
    needs_hover = False

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        self.to = float(objective.get("toM", 200.0))
        self.back_to = float(objective.get("fromM", 10.0))
        self.cycles = max(1, int(objective.get("cycles", 1)))
        self.limit = float(objective.get("timeLimitS", 7200.0))
        self.deepest = 0.0
        self.shallowest = 1e9
        self.legs = 0                       # half a sawtooth each
        self.descending = True
        self.turned_at: list[float] = []

    def judge(self, elapsed, position, heading, floor) -> None:
        depth = float(-position[2])
        self.deepest = max(self.deepest, depth)
        self.shallowest = min(self.shallowest, depth)
        if self.descending and depth >= self.to:
            self.descending = False
            self.legs += 1
            self.turned_at.append(round(elapsed, 1))
        elif not self.descending and depth <= self.back_to:
            self.descending = True
            self.legs += 1
            self.turned_at.append(round(elapsed, 1))
        if self.legs >= self.cycles * 2 or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        return min(1.0, self.legs / float(self.cycles * 2))

    def says(self) -> str:
        return (f"{self.legs // 2} of {self.cycles} profiles, "
                f"{self.deepest:.0f} m deepest")

    def detail(self) -> dict:
        return {"cycles": self.cycles, "legs": self.legs,
                "completed": self.legs // 2,
                "toM": self.to, "fromM": self.back_to,
                "deepestM": round(self.deepest, 1),
                "shallowestM": round(self.shallowest, 1) if self.shallowest < 1e8 else None,
                "turnedAtS": self.turned_at[:60]}

    def goal(self) -> dict:
        return {"kind": "profile", "bandM": [self.back_to, self.to], "cycles": self.cycles}

    def failed(self) -> bool:
        return self.done and self.score() < 0.999


class Section(Task):
    """A sawtooth along a line: profiles, one after another, going somewhere.

    What a glider is actually sent out to do. The vehicle is given a line and a
    depth band and it saws its way along, and the science is the column against
    distance. It is also where the current stops being a nuisance and becomes
    the result — a glider that is set down on the wrong end of a knot does not
    arrive, and where it ends up instead is the measurement.
    """

    kind = "section"
    name = "Fly a section"
    needs_hover = False

    def __init__(self, objective, began_at, heading) -> None:
        super().__init__(objective, began_at, heading)
        band = objective.get("bandM") or [10.0, 200.0]
        self.shallow, self.deep = float(min(band)), float(max(band))
        self.limit = float(objective.get("timeLimitS", 14400.0))
        toward = self.somewhere(objective.get("toward"),
                                self.out_from_start(1000.0, 0.0))
        self.toward = np.asarray(toward, dtype=float)
        self.line = self.toward[:2] - self.began_at[:2]
        self.length = float(np.hypot(*self.line)) or 1.0
        self.along_unit = self.line / self.length
        # How finely the column has to be sampled for the section to be worth
        # having. Stated as the distance between profiles, because that is what
        # an oceanographer asks for: a Red Sea eddy is a few kilometres across
        # and a profile every ten would not see one.
        self.every = float(objective.get("profileEveryM", 0.0))
        self.wanted_profiles = (self.length / self.every) if self.every > 0 else 0.0
        self.furthest = 0.0
        self.off_line = 0.0
        self.worst_off = 0.0
        self.legs = 0
        self.descending = True

    def judge(self, elapsed, position, heading, floor) -> None:
        rel = position[:2] - self.began_at[:2]
        along = float(np.dot(rel, self.along_unit))
        self.furthest = max(self.furthest, along)
        # The 2-D cross product, written out. numpy dropped cross() on
        # two-vectors, and it is one multiplication either way.
        self.off_line = float(abs(self.along_unit[0] * rel[1]
                                  - self.along_unit[1] * rel[0]))
        self.worst_off = max(self.worst_off, self.off_line)
        depth = float(-position[2])
        if self.descending and depth >= self.deep:
            self.descending = False
            self.legs += 1
        elif not self.descending and depth <= self.shallow:
            self.descending = True
            self.legs += 1
        if self.furthest >= self.length or elapsed >= self.limit:
            self.done = True

    def score(self) -> float:
        """Distance along the line, and whether the profiles are usable.

        Getting there is half of it. A section is a picture of the water
        column against distance, and a glider that covers the ground but
        profiles it every four kilometres has brought back a picture with
        nothing in it — the eddy it was sent to find is two kilometres across
        and falls between the teeth. Profiles too far apart to resolve what
        was being looked for is a failed section that looks like a successful
        transit.
        """
        got_there = float(min(1.0, max(0.0, self.furthest / self.length)))
        return got_there * self.resolution()

    def resolution(self) -> float:
        """How much of the asked-for sampling it actually delivered."""
        if self.wanted_profiles <= 0:
            return 1.0
        return float(min(1.0, (self.legs / 2.0) / self.wanted_profiles))

    def says(self) -> str:
        return (f"{self.furthest:.0f} m of {self.length:.0f} along, "
                f"{self.legs // 2} of {self.wanted_profiles:.0f} profiles, "
                f"{self.off_line:.0f} m off the line")

    def detail(self) -> dict:
        return {"alongM": round(self.furthest, 1), "lengthM": round(self.length, 1),
                "fraction": round(self.score(), 3),
                "alongFraction": round(min(1.0, self.furthest / self.length), 3),
                "profiles": self.legs // 2,
                "profilesWanted": round(self.wanted_profiles, 1) or None,
                "profileEveryM": round(self.furthest / max(1, self.legs // 2), 1)
                                 if self.legs >= 2 else None,
                "resolution": round(self.resolution(), 3),
                "bandM": [self.shallow, self.deep],
                "offLineM": round(self.off_line, 1),
                "worstOffLineM": round(self.worst_off, 1)}

    def geometry(self) -> dict:
        return {"path": [{"x": float(self.began_at[0]), "y": float(self.began_at[1])},
                         {"x": float(self.toward[0]), "y": float(self.toward[1])}]}

    def goal(self) -> dict:
        return {"kind": "section", "to": [float(v) for v in self.toward[:2]],
                "bandM": [self.shallow, self.deep]}

    def failed(self) -> bool:
        return self.done and self.score() < 0.9


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

    def goal(self) -> dict:
        return {"kind": "circle", "at": [float(v) for v in self.target],
                "radiusM": self.radius, "sectors": self.SECTORS}

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

    def goal(self) -> dict:
        # Held at, not merely passed over: the sample is the ten seconds, and
        # the goal says so rather than leaving it to a route to imply.
        return {"kind": "visit", "points": [[float(v) for v in m] for m in self.marks],
                "radiusM": self.reach, "holdS": self.hold_for}

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

    def goal(self) -> dict:
        return {"kind": "hold", "at": [float(v) for v in self.began_at]}

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

    def goal(self) -> dict:
        stage = self.stage
        return {} if stage is None else stage.goal()

    def goal_id(self) -> str:
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
         "outplant": Outplant, "monitor": Monitor,
         "profile": Profile, "section": Section,
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
    if made is Monitor:
        return Monitor(objective, began_at, heading, camera=camera, colonies=colonies)
    if made is Search:
        return Search(objective, began_at, heading, camera=camera)
    if made is Inspect:
        return Inspect(objective, began_at, heading, camera=camera)
    if made is Treat:
        return Treat(objective, began_at, heading, colonies=colonies)
    return made(objective, began_at, heading)
