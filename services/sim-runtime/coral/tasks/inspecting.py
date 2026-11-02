"""Inspecting something long: a pipeline followed from end to end.

A pipeline is inspected for what is wrong along it, and the commonest thing
wrong with one on a seabed is a free span: a stretch it bridges with nothing
under it, which vibrates in a current until it fatigues. So the inspection is
scored on two counts. How much of the line the camera saw at the height it was
asked to look from. And which of its free spans (world.Laid) it saw, since a
survey that covered ninety per cent of the line and missed the two spans has
missed the point.

And it is tracked, not flown from the chart. A chart puts a line where it was
meant to go, and one laid twenty years ago is metres from there; a vehicle
flying the chart's line with a camera two metres over the bottom sees sand
beside the pipe. So the vehicle is told the line as charted (chartErrorM is how
wrong that is, which only the judge knows), sweeps across it until the camera
has the pipe (searchM), and moves its line onto what it saw each time the two
differ by more than half a metre. Where the pipe goes under the sand the camera
has nothing, and the vehicle holds the line it last had, as a tracker does.
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
        self.backwards: bool | None = None
        # The line as the vehicle was told it: the true one moved by how wrong
        # the chart is. And how far it has since moved it, from what it saw.
        self.chart_error = np.array((list(objective.get("chartErrorM") or []) + [0.0, 0.0])[:2], dtype=float)
        self.search = float(objective.get("searchM", 0.0))
        self.noise = float(objective.get("sightingNoiseM", 0.15))
        self.rng = np.random.default_rng(int(objective.get("seed", 7)))
        self.shift = np.zeros(2)
        self.flown_shift = np.zeros(2)
        self.version = 0
        self.planned_at = -1e9
        self.acquired: dict | None = None
        self.sighted: list[float] = []
        self.out = np.ones(len(self.at), dtype=bool)
        if self.line is not None and hasattr(self.over, "is_exposed"):
            self.out = np.array([self.over.is_exposed(float(a)) for a in self.at], dtype=bool)
        # What is on the line, where along it, and whether the camera had it.
        self.features = []
        for one in getattr(self.over, "features", []) or []:
            if self.line is None:
                break
            k = int(np.argmin(np.abs(self.at - float(one.get("atM", 0.0)))))
            self.features.append({**one, "xy": self.line[k, :2].copy(), "z": float(self.line[k, 2]),
                                  "exposed": bool(self.out[k]), "found": None})

    def believed_line(self) -> np.ndarray:
        """Where the vehicle thinks the line is: the chart's, moved by what it saw."""
        return self.line[:, :2] + self.chart_error + self.shift

    def planned_line(self):
        # The line as it is believed, flown at its offset to one side.
        return None if self.line is None else (self.believed_line(), abs(self.offset))

    def judge(self, elapsed, position, heading, floor) -> None:
        if self.line is not None:
            flat = np.hypot(self.line[:, 0] - position[0], self.line[:, 1] - position[1])
            above = position[2] - self.line[:, 2]
            looking = (flat <= self.half_swath) & (above > 0.0) & (np.abs(above - self.altitude) <= self.band)
            self.seen |= looking
            self.sight(elapsed, position, flat, looking)
        far_seen = self.far_end is not None and bool(self.seen[self.far_end])
        if self.line is None or self.seen.all() or far_seen or elapsed >= self.limit:
            self.done = True

    def sight(self, elapsed, position, flat, looking) -> None:
        """What the camera shows: the pipe where it is out of the sand and in view.

        A sighting is where the pipe is across the image, which is a measured
        offset from the line the vehicle is flying, with the error of reading
        it off a picture (sightingNoiseM). Folded into the line it believes."""
        visible = looking & self.out
        if visible.any():
            k = int(np.flatnonzero(visible)[np.argmin(flat[visible])])
            # Seen from where the vehicle is, so in the frame it believes it is
            # in: its navigation's error is in the line it moves to.
            told = self.line[k, :2] + self.chart_error
            wrong = (self.believed[:2] - position[:2]) if self.believed is not None else np.zeros(2)
            measured = self.line[k, :2] + wrong - told + self.rng.normal(0.0, self.noise, 2)
            first = self.acquired is None
            self.shift = measured if first else 0.7 * self.shift + 0.3 * measured
            self.sighted.append(float(self.at[k]))
            if first:
                self.acquired = {"atS": round(float(elapsed), 1), "alongM": round(float(self.at[k]), 1)}
                self.version += 1
            elif (float(np.linalg.norm(self.shift - self.flown_shift)) > 0.5
                  and elapsed - self.planned_at >= 5.0):
                self.version += 1
        believed_offset = (self.believed - position) if self.believed is not None else np.zeros(3)
        for one in self.features:
            if one["found"] is not None or not one["exposed"]:
                continue
            near = float(np.hypot(*(one["xy"] - position[:2])))
            above = position[2] - one["z"]
            if near <= self.half_swath and above > 0.0 and abs(above - self.altitude) <= self.band:
                logged = one["xy"] + believed_offset[:2]
                one["found"] = {"atS": round(float(elapsed), 1),
                                "loggedAt": [round(float(logged[0]), 1), round(float(logged[1]), 1)],
                                "offByM": round(float(np.linalg.norm(believed_offset[:2])), 2)}

    def goal_id(self) -> str:
        return f"{self.kind}-{self.version}"

    def exposed_m(self) -> float:
        if len(self.at) < 2:
            return 0.0
        both = self.out[1:] & self.out[:-1]
        return float(np.sum(np.diff(self.at)[both]))

    def exposed_seen_m(self) -> float:
        if len(self.at) < 2:
            return 0.0
        both = self.seen[1:] & self.seen[:-1] & self.out[1:] & self.out[:-1]
        return float(np.sum(np.diff(self.at)[both]))

    def seen_exposed(self) -> list[dict]:
        """Where along the line the camera had the pipe, as runs: what the
        inspection reports as exposed. A gap of more than three metres between
        sightings ends a run."""
        runs: list[list[float]] = []
        for at in sorted(self.sighted):
            if runs and at - runs[-1][1] <= 3.0:
                runs[-1][1] = at
            else:
                runs.append([at, at])
        return [{"fromM": round(a, 1), "toM": round(b, 1)} for a, b in runs if b - a >= 1.0]

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
        # The line where there is a pipe to see; all of it when none is buried.
        exposed = self.exposed_m()
        covered = self.exposed_seen_m() / exposed if exposed > 0.0 else self.seen_m() / self.length()
        parts = [covered]
        # The spans and what is on the line count as much as the line does:
        # they are why it is flown.
        spans = self.spans_seen()
        if spans:
            parts.append(sum(one["seen"] for one in spans) / len(spans))
        findable = [one for one in self.features if one["exposed"]]
        if findable:
            parts.append(sum(one["found"] is not None for one in findable) / len(findable))
        return parts[0] if len(parts) == 1 else 0.5 * parts[0] + 0.5 * sum(parts[1:]) / len(parts[1:])

    def says(self) -> str:
        spans = self.spans_seen()
        said = (f"{self.seen_m():.0f} of {self.length():.0f} m of the line seen; "
                f"{sum(one['seen'] for one in spans)} of {len(spans)} free spans")
        if self.features:
            findable = [one for one in self.features if one["exposed"]]
            said += f"; {sum(one['found'] is not None for one in findable)} of {len(findable)} things on it found"
        if self.acquired is not None:
            said += f"; the pipe was {float(np.linalg.norm(self.shift)):.1f} m from the chart"
        return said

    def detail(self) -> dict:
        said = {"lengthM": round(self.length(), 1), "seenM": round(self.seen_m(), 1),
                "altitudeM": self.altitude, "swathM": round(2 * self.half_swath, 2),
                "freeSpans": self.spans_seen()}
        if self.search or self.chart_error.any() or self.features or not self.out.all():
            said.update({
                "exposedM": round(self.exposed_m(), 1),
                "exposedSeenM": round(self.exposed_seen_m(), 1),
                # What the camera found, which is the inspection's report.
                "seenExposed": self.seen_exposed(),
                "acquired": self.acquired,
                "chartOffM": {"value": [round(float(v), 2) for v in self.shift], "kind": "derived",
                              "from": "the camera's sightings of the pipe against the line it was told"},
                "replanned": self.version,
                "features": [{key: one[key] for key in ("id", "what", "atM") if key in one}
                             | {"found": one["found"], "exposed": one["exposed"]} for one in self.features]})
        return said

    def route_points(self) -> list:
        """Along the believed line every ten metres, at its own height, from
        the nearer end; from where the vehicle is when it is planned again; and
        across the line first while the camera has not yet had the pipe."""
        if self.line is None:
            return []
        keep = [0]
        for k in range(1, len(self.at)):
            if self.at[k] - self.at[keep[-1]] >= 10.0:
                keep.append(k)
        if keep[-1] != len(self.at) - 1:
            keep.append(len(self.at) - 1)
        points = self.line[keep].copy()
        points[:, :2] = self.believed_line()[keep]
        way = np.gradient(points[:, :2], axis=0)
        norm = np.linalg.norm(way, axis=1, keepdims=True)
        norm[norm < 1e-9] = 1.0
        side = np.column_stack([way[:, 1], -way[:, 0]]) / norm
        if self.offset:
            points[:, :2] += side * self.offset
        here = self.believed if self.believed is not None else self.began_at
        if self.backwards is None:
            self.backwards = bool(np.linalg.norm(points[-1, :2] - here[:2]) < np.linalg.norm(points[0, :2] - here[:2]))
        if self.backwards:
            points, side = points[::-1], side[::-1]
        self.far_end = 0 if self.backwards else len(self.line) - 1
        if self.version > 0:
            # Planned again: on from the point ahead of where it is now.
            k = int(np.argmin(np.hypot(points[:, 0] - here[0], points[:, 1] - here[1])))
            points, side = points[min(k + 1, len(points) - 1):], side[min(k + 1, len(points) - 1):]
        elif self.search > 0.0 and len(points) >= 2:
            # Across the line and back, eight metres along each sweep, for the
            # first forty metres or until the pipe is in view.
            first, ahead = points[0], points[1] - points[0]
            ahead = ahead / max(float(np.linalg.norm(ahead[:2])), 1e-9)
            across = np.array([ahead[1], -ahead[0], 0.0])
            sweep = [first + ahead * (8.0 * n) + across * (self.search if n % 2 else -self.search)
                     for n in range(1, 6)]
            beyond = [p for p in points if float(np.dot(p[:2] - first[:2], ahead[:2])) > 44.0]
            points = np.array([first] + sweep + beyond)
        self.flown_shift = self.shift.copy()
        self.planned_at = self.elapsed()
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
