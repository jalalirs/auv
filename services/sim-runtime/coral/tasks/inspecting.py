"""Inspecting something long: a pipeline followed from end to end.

A pipeline is inspected for what is wrong along it, and the commonest thing
wrong with one on a seabed is a free span: a stretch it bridges with nothing
under it, which vibrates in a current until it fatigues. So the inspection is
scored on two counts. How much of the line the camera saw at the height it was
asked to look from. And which of its free spans (world.Laid) it saw, since a
survey that covered ninety per cent of the line and missed the two spans has
missed the point.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Task, footprint_half_angle


class FollowLine(Task):
    kind = "follow"
    name = "Follow a line"
    flies_through = True
    wants = ("camera",)

    def __init__(self, objective, began_at, heading, camera=None, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.altitude = float(objective.get("altitudeM", 2.0))
        self.band = float(objective.get("altitudeBandM", 1.0))
        self.offset = float(objective.get("offsetM", 0.0))
        self.limit = float(objective.get("timeLimitS", 3600.0))
        # How wide the camera sees across the line at that height; its own
        # field of view when it has said one, otherwise a swath it is given.
        half = footprint_half_angle(camera)
        self.half_swath = (self.altitude * math.tan(half) if half is not None
                           else 0.5 * float(objective.get("swathM", 3.0)))
        self.line = None
        self.at = np.zeros(0)
        self.seen = np.zeros(0, dtype=bool)
        if self.over is not None and getattr(self.over, "curve", None):
            curve = np.array(self.over.curve, dtype=float)
            # Sampled every half metre, so what was seen is a length.
            parts = [curve[0]]
            for one, two in zip(curve, curve[1:]):
                n = max(1, int(math.ceil(float(np.linalg.norm(two[:2] - one[:2])) / 0.5)))
                parts += [one + (two - one) * (k / n) for k in range(1, n + 1)]
            self.line = np.array(parts)
            step = np.linalg.norm(np.diff(self.line[:, :2], axis=0), axis=1)
            self.at = np.concatenate([[0.0], np.cumsum(step)])
            self.seen = np.zeros(len(self.line), dtype=bool)
        self.spans = list(getattr(self.over, "spans", []) or [])
        # Which end it is flown towards, once the route is drawn: the inspection
        # is over when that end has been seen, rather than circling at it until
        # the clock runs out for the few metres seen badly on the way down.
        self.far_end: int | None = None

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.line is not None:
            flat = np.hypot(self.line[:, 0] - position[0], self.line[:, 1] - position[1])
            above = position[2] - self.line[:, 2]
            looking = (flat <= self.half_swath) & (above > 0.0) & (np.abs(above - self.altitude) <= self.band)
            self.seen |= looking
        far_seen = self.far_end is not None and bool(self.seen[self.far_end])
        if self.line is None or self.seen.all() or far_seen or elapsed >= self.limit:
            self.done = True

    def length(self) -> float:
        return float(self.at[-1]) if len(self.at) else 0.0

    def seen_m(self) -> float:
        if len(self.at) < 2:
            return 0.0
        both = self.seen[1:] & self.seen[:-1]
        return float(np.sum(np.diff(self.at)[both]))

    def spans_seen(self) -> list[dict]:
        out = []
        for span in self.spans:
            inside = (self.at >= span["fromM"]) & (self.at <= span["toM"])
            share = float(self.seen[inside].mean()) if inside.any() else 0.0
            out.append({**span, "seenShare": round(share, 2), "seen": share >= 0.5})
        return out

    def score(self) -> float:
        if self.length() <= 0.0:
            return 0.0
        covered = self.seen_m() / self.length()
        spans = self.spans_seen()
        if not spans:
            return covered
        # Half for the line and half for the spans: the spans are why it is flown.
        return 0.5 * covered + 0.5 * sum(one["seen"] for one in spans) / len(spans)

    def says(self) -> str:
        spans = self.spans_seen()
        return (f"{self.seen_m():.0f} of {self.length():.0f} m of the line seen; "
                f"{sum(one['seen'] for one in spans)} of {len(spans)} free spans")

    def detail(self) -> dict:
        return {"lengthM": round(self.length(), 1), "seenM": round(self.seen_m(), 1),
                "altitudeM": self.altitude, "swathM": round(2 * self.half_swath, 2),
                "freeSpans": self.spans_seen()}

    def route_points(self) -> list:
        """Along the line every ten metres, at its own height, from the nearer end."""
        if self.line is None:
            return []
        keep = [0]
        for k in range(1, len(self.at)):
            if self.at[k] - self.at[keep[-1]] >= 10.0:
                keep.append(k)
        if keep[-1] != len(self.at) - 1:
            keep.append(len(self.at) - 1)
        points = self.line[keep]
        if self.offset:
            way = np.gradient(points[:, :2], axis=0)
            norm = np.linalg.norm(way, axis=1, keepdims=True)
            norm[norm < 1e-9] = 1.0
            side = np.column_stack([way[:, 1], -way[:, 0]]) / norm
            points = points.copy()
            points[:, :2] += side * self.offset
        here = self.believed if self.believed is not None else self.began_at
        backwards = np.linalg.norm(points[-1, :2] - here[:2]) < np.linalg.norm(points[0, :2] - here[:2])
        if backwards:
            points = points[::-1]
        self.far_end = 0 if backwards else len(self.line) - 1
        # At the height asked for above the line itself, as a pipe tracker
        # holds it, not above whatever the altimeter sees: over a fore-reef
        # the altimeter sees colony tops, and a REMUS keeping 4.5 m over them
        # rode too high over the pipe for the camera and missed a span.
        return [[float(p[0]), float(p[1]), float(p[2]) + self.altitude] for p in points]

    def geometry(self) -> dict:
        if self.line is None:
            return {}
        return {"route": [{"x": float(p[0]), "y": float(p[1])} for p in self.line[::20]]}

    def goal(self) -> dict:
        return {"kind": "visit", "points": self.route_points(), "radiusM": 2.0}
