"""Doing something to something.

These are the tasks a reef programme actually pays for, and the ones where the
score is a count of things rather than a distance: colonies treated, corals
planted, plots read, a structure inspected, a site revisited to see what
changed. They are also the tasks that need to know where the coral is, which is
why they take `colonies`.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Task, footprint_half_angle, wrap


class Treat(Task):
    """Go over every colony in a patch, low enough and slow enough to do
    something about it.

    This is the task the place makes possible: the colonies are the ones the
    survey found, at the positions it found them, so covering them is covering
    real coral and the score is a share of a real population. A colony counts
    as treated when the vehicle passes within reach of it while low enough and
    slow enough for whatever it is carrying to work.
    """

    wants = ("colonies",)
    kind = "treat"
    name = "Treat the coral"

    def __init__(self, objective, began_at, heading, colonies=None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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

    wants = ("camera", "colonies")
    kind = "monitor"
    name = "Monitor a grid cell"

    CELL = 0.5

    def __init__(self, objective, began_at, heading, camera: dict | None = None,
                 colonies=None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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


class Inspect(Task):
    """Go round a thing, keeping it in frame from a fixed distance.

    Scored on how much of the way round was actually seen: the circle is cut
    into sectors, and a sector counts when the vehicle was in it, at about the
    right distance, with the thing in front of it. Which is what an inspection
    is — not a lap, a look at every side.
    """

    wants = ("camera",)
    kind = "inspect"
    name = "Inspect"

    SECTORS = 12

    def __init__(self, objective, began_at, heading, camera: dict | None = None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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

    def __init__(self, objective, began_at, heading, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
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
