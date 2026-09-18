"""Covering ground, or covering water.

What these have in common is that the answer is a fraction of something: how
much of the bottom the camera's footprint fell on, how much of the column was
sampled, how much of the box was looked in. None of them is scored on arriving
anywhere — a vehicle that flew the whole box and saw a third of it did a third
of the job.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Task, footprint_half_angle


class Survey(Task):
    """Cover a rectangle. What counts as seen is what the camera's footprint
    on the bottom covered at each pose — derived from the poses and the
    camera, not asserted — when the vehicle carries a camera the catalogue
    describes; a fixed swath otherwise."""

    wants = ("camera",)
    stops_a_mission = False
    kind = "survey"
    name = "Survey"

    CELL = 0.5

    def __init__(self, objective, began_at, heading, camera: dict | None = None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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
        # Pointed at a plot somebody drew: the box is the plot. Same rule —
        # what is scored is still the share of the box the camera's footprint
        # fell on — but the box is now a thing with corners on a chart instead
        # of a rectangle laid out ahead of wherever the vehicle happened to
        # start and aimed by whatever heading it happened to have.
        box = None if self.over is None else self.box_of(self.over)
        if box is not None:
            middle, east, north = box
            self.width, self.height = east, north
            self.u = np.array([1.0, 0.0])      # the corners are east and north
            self.v = np.array([0.0, -1.0])
            self.began_at = np.array([middle[0] - east / 2.0, middle[1] + north / 2.0,
                                      float(self.began_at[2])])
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

    wants = ("camera",)
    stops_a_mission = False
    kind = "search"
    name = "Find it"

    def __init__(self, objective, began_at, heading, camera: dict | None = None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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


class Profile(Task):
    """Down to a depth and back. The unit a glider mission is built from.

    Everything a buoyancy glider does is made of these: it cannot hold a depth
    and it cannot stop, so the only thing it can be asked for is the shape of
    the sawtooth and how many teeth. What comes back is a column of water
    measured top to bottom, which is what an oceanographer wanted in the first
    place.
    """

    stops_a_mission = False
    kind = "profile"
    name = "Profile the water column"
    needs_hover = False

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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

    stops_a_mission = False
    kind = "section"
    name = "Fly a section"
    needs_hover = False

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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
