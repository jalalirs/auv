"""What is in the water besides the vehicle.

A place is a seabed and its coral, and both are read from a survey. That is the
right foundation and it is not a site. What a dive actually happens in is a
site somebody *arranged*: an array laid in a particular pattern, a ship holding
station over there, a nursery frame here, a line running between those two
points. None of it is in the survey, all of it is in the water, and a vehicle
flown through it has to be able to run into it.

This is where those live. It is a module rather than eleven more methods on the
dive because everything about the world that is still to come — lines that bow
with the current, a tether that pulls back, things that move — lands here, and
a class with fifty-nine methods does not want twelve more.

Two things it does, and they are separate on purpose:

  **Truth.** Where each thing is, in the world's own coordinates, resolved when
  it was drawn rather than when it is flown. A task scores against this, and a
  sonar will eventually see it.

  **Obstruction.** A vehicle driven at a mooring block stops, the same way it
  stops against the ground — two constraints resolved by putting the vehicle
  back where it was allowed to be and taking away the velocity that carried it
  out. Not a collision solver: a hard stop does not bounce and does not keep
  pushing.
"""

from __future__ import annotations

import math

import numpy as np

# The palette: every kind of thing somebody can put in the water, how it meets
# the bottom, and how big it is. Coarse on purpose — what matters to a vehicle
# at half a metre a second is whether something is there, not the shape of its
# corners — but the *landing rule* is not coarse at all, because it is the one
# thing the editor has to resolve and the one thing a layout would otherwise
# mean two different depths for.
#
#   ground    Sits on the bottom. Its depth is the seabed under it, and the
#             thing stands up from there.
#   surface   Floats. Its depth is zero and the thing hangs *down* — a ship at
#             the surface is three metres of hull in the water, not three
#             metres of air.
#   span      Two ends, each landed by its own rule, and a line between them
#             that hangs by however much slack it was given.
#   region    An area drawn on the chart. Nothing to run into: a boundary is a
#             thing a task points at, not a thing in the water.


class Kind:
    """What a kind of thing is, said once."""

    __slots__ = ("lands", "radius", "height", "what")

    def __init__(self, lands: str, radius: float, height: float, what: str) -> None:
        self.lands, self.radius, self.height, self.what = lands, radius, height, what


KINDS = {
    "transponder":      Kind("ground",  0.35, 2.0,  "an LBL transponder on its stand"),
    "mooring-block":    Kind("ground",  0.8,  0.6,  "a concrete block holding a line down"),
    "nursery-frame":    Kind("ground",  2.0,  1.2,  "a frame of coral growing on"),
    "marker-post":      Kind("ground",  0.2,  3.0,  "a post marking a plot"),
    "buoy":             Kind("surface", 0.5,  0.8,  "a buoy on the surface"),
    "ship":             Kind("surface", 6.0,  3.0,  "a ship holding station"),
    "mooring-line":     Kind("span",    0.05, 0.0,  "a line between two points"),
    "restoration-cell": Kind("region",  0.0,  0.0,  "a plot somebody works inside"),
}
DEFAULT = Kind("ground", 0.6, 1.0, "something")


def _catenary(a_end, b_end, slack: float, step: float = 1.0):
    """The shape a line takes between two points when it is longer than the gap.

    A mooring riser from a block to a surface buoy is nearly taut and nearly
    straight. A line strung between two blocks with ten per cent of slack in it
    bows down in the middle, and how far down is not a guess: a uniform line
    hanging under its own weight is a catenary, and the catenary through two
    points with a given arc length is determined. Solving for it is worth the
    twenty lines because the sag is the part a vehicle flies into.

    Answers the points along it, ends included.
    """
    a_end = np.asarray(a_end, dtype=float)
    b_end = np.asarray(b_end, dtype=float)
    flat = float(np.hypot(b_end[0] - a_end[0], b_end[1] - a_end[1]))
    rise = float(b_end[2] - a_end[2])
    straight = float(np.linalg.norm(b_end - a_end))
    length = straight * (1.0 + max(0.0, slack))
    count = max(2, int(straight / max(0.2, step)) + 1)
    walk = np.linspace(0.0, 1.0, count)
    # Taut, or hanging straight down: a straight line is the answer and the
    # catenary solution is undefined there anyway.
    if length <= straight + 1e-6 or flat < 1e-3 or length <= abs(rise):
        return [a_end + (b_end - a_end) * f for f in walk]

    # Solve 2a·sinh(h/2a) = sqrt(L² − v²) for the catenary parameter. The left
    # side falls from infinity to h as a grows, so it is a bisection.
    want = math.sqrt(max(0.0, length * length - rise * rise))
    low, high = 1e-4, max(1.0, flat)
    while 2.0 * high * math.sinh(flat / (2.0 * high)) > want:
        high *= 2.0
        if high > 1e7:
            return [a_end + (b_end - a_end) * f for f in walk]
    for _ in range(80):
        mid = 0.5 * (low + high)
        if 2.0 * mid * math.sinh(flat / (2.0 * mid)) > want:
            low = mid
        else:
            high = mid
    a = 0.5 * (low + high)
    offset = flat / 2.0 - a * math.atanh(max(-0.999999, min(0.999999, rise / length)))
    base = a_end[2] - a * math.cosh(-offset / a)
    out = []
    for f in walk:
        along = flat * f
        out.append(np.array([a_end[0] + (b_end[0] - a_end[0]) * f,
                             a_end[1] + (b_end[1] - a_end[1]) * f,
                             base + a * math.cosh((along - offset) / a)]))
    return out


class Thing:
    """One thing somebody put in the water.

    Three shapes, because three is what the palette needs and one with flags
    would be one that needs a fourth flag next month: something standing at a
    point, something spanning between two, and an area drawn on the chart.
    """

    __slots__ = ("id", "kind", "said", "spec")

    def __init__(self, said: dict) -> None:
        self.said = dict(said)
        self.id = str(said.get("id") or "")
        self.kind = str(said.get("kind") or "thing")
        self.spec = KINDS.get(self.kind, DEFAULT)

    @staticmethod
    def of(said: dict) -> "Thing":
        """The right shape for what this is."""
        lands = KINDS.get(str(said.get("kind") or ""), DEFAULT).lands
        if lands == "span":
            return Spanning(said)
        if lands == "region":
            return Region(said)
        return Standing(said)

    # Every thing answers these three. A vehicle asks the first two and the
    # record asks the third; nothing outside this module asks what shape it is.

    def near(self, position, margin: float = 0.0) -> bool:
        return False

    def push_out(self, position, was, half_width: float):
        return position

    def described(self) -> dict:
        return {"id": self.id, "kind": self.kind, "is": self.spec.what}


class Standing(Thing):
    """A cylinder at a point: most of the palette.

    Landed when it was drawn, not now. `z` is what the editor's rule resolved
    against that seabed — which is why a layout belongs to a place and is wrong
    anywhere else — in the world's own frame: metres, origin at the middle of
    the site, +x east, +y north, the frame a vehicle's positions are in. No
    conversion here on purpose: a layout read in one frame and flown in another
    is a layout that looks right in the editor and is somewhere else in the
    water.

    The vertical extent follows the landing rule. Something on the ground
    stands up from it; something on the surface hangs down from it. A ship
    whose three metres went upward would be three metres of sky that a vehicle
    at two metres deep flew straight through.
    """

    __slots__ = ("at", "radius", "height", "low", "high")

    def __init__(self, said: dict) -> None:
        super().__init__(said)
        z = said.get("z")
        if z is None:
            ground = said.get("groundM")
            z = 0.0 if self.spec.lands == "surface" else (
                -float(ground) if ground is not None else 0.0)
        self.at = np.array([float(said.get("x", 0.0)), float(said.get("y", 0.0)),
                            float(z)], dtype=float)
        self.radius = float(said.get("radiusM", self.spec.radius))
        self.height = float(said.get("heightM", self.spec.height))
        if self.spec.lands == "surface":
            self.low, self.high = self.at[2] - self.height, self.at[2]
        else:
            self.low, self.high = self.at[2], self.at[2] + self.height

    def near(self, position, margin: float = 0.0) -> bool:
        flat = float(np.hypot(position[0] - self.at[0], position[1] - self.at[1]))
        if flat > self.radius + margin:
            return False
        return (self.low - margin) <= float(position[2]) <= (self.high + margin)

    def push_out(self, position, was, half_width: float):
        # Out the way it came in. Pushing it to the nearest face would slide a
        # vehicle round an obstacle it drove straight at, which is a vehicle
        # passing through something slowly.
        away = np.array([position[0] - self.at[0], position[1] - self.at[1], 0.0])
        flat = float(np.hypot(away[0], away[1]))
        if flat < 1e-6:
            away = np.array([float(was[0] - self.at[0]),
                             float(was[1] - self.at[1]), 0.0])
            flat = float(np.hypot(away[0], away[1])) or 1.0
        out = np.asarray(position, dtype=float).copy()
        reach = self.radius + half_width
        out[0] = self.at[0] + away[0] / flat * reach
        out[1] = self.at[1] + away[1] / flat * reach
        return out

    def described(self) -> dict:
        said = super().described()
        said.update({"at": [round(float(v), 2) for v in self.at],
                     "radiusM": round(self.radius, 2),
                     "heightM": round(self.height, 2)})
        return said


class Spanning(Thing):
    """A line between two points, hanging by whatever slack it has.

    The one kind with real work in it, because it is not anywhere: it is
    everywhere along a curve, and a vehicle flying under a mooring line at the
    middle of the span meets it lower than the map says it is.
    """

    __slots__ = ("a", "b", "radius", "curve", "slack")

    def __init__(self, said: dict) -> None:
        super().__init__(said)
        ends = said.get("ends") or []
        first = ends[0] if len(ends) > 0 else {}
        second = ends[1] if len(ends) > 1 else {}
        self.a = self._end(first)
        self.b = self._end(second)
        self.slack = float(said.get("slack", 0.0))
        self.radius = float(said.get("radiusM", self.spec.radius))
        self.curve = _catenary(self.a, self.b, self.slack)

    @staticmethod
    def _end(said: dict) -> np.ndarray:
        z = said.get("z")
        if z is None:
            ground = said.get("groundM")
            z = -float(ground) if ground is not None else 0.0
        return np.array([float(said.get("x", 0.0)), float(said.get("y", 0.0)),
                         float(z)], dtype=float)

    def _nearest(self, position):
        """The closest point on the line, and how far off it is."""
        point = np.asarray(position, dtype=float)
        best, best_away = self.curve[0], float("inf")
        for one, two in zip(self.curve, self.curve[1:]):
            leg = two - one
            length = float(np.dot(leg, leg))
            f = 0.0 if length < 1e-12 else max(0.0, min(1.0, float(np.dot(point - one, leg)) / length))
            on = one + leg * f
            away = float(np.linalg.norm(point - on))
            if away < best_away:
                best, best_away = on, away
        return best, best_away

    def near(self, position, margin: float = 0.0) -> bool:
        return self._nearest(position)[1] <= self.radius + margin

    def push_out(self, position, was, half_width: float):
        on, away = self._nearest(position)
        out = np.asarray(position, dtype=float) - on
        length = float(np.linalg.norm(out))
        if length < 1e-6:
            out = np.asarray(was, dtype=float) - on
            length = float(np.linalg.norm(out)) or 1.0
        return on + out / length * (self.radius + half_width)

    def described(self) -> dict:
        said = super().described()
        deepest = min(float(p[2]) for p in self.curve)
        said.update({"from": [round(float(v), 2) for v in self.a],
                     "to": [round(float(v), 2) for v in self.b],
                     "slack": round(self.slack, 3),
                     "lowestM": round(-deepest, 2),
                     "radiusM": round(self.radius, 3)})
        return said


class Region(Thing):
    """An area drawn on the chart. A plot, not an obstacle.

    Nothing to run into — a boundary somebody drew is a thing a task points at
    ("plant inside this cell", "cover this and nothing else"), and a vehicle
    that bounced off one would be a vehicle bouncing off a line on a map.
    """

    __slots__ = ("corners",)

    def __init__(self, said: dict) -> None:
        super().__init__(said)
        self.corners = [np.array([float(c.get("x", 0.0)), float(c.get("y", 0.0))])
                        for c in (said.get("corners") or [])]

    def contains(self, position) -> bool:
        """Whether a point is inside, by the crossing rule. Depth is not asked:
        a plot is an area of seabed and a vehicle over it is over it."""
        if len(self.corners) < 3:
            return False
        x, y = float(position[0]), float(position[1])
        inside = False
        for one, two in zip(self.corners, self.corners[1:] + self.corners[:1]):
            if (one[1] > y) != (two[1] > y):
                cut = one[0] + (y - one[1]) * (two[0] - one[0]) / (two[1] - one[1])
                if x < cut:
                    inside = not inside
        return inside

    def area_m2(self) -> float:
        if len(self.corners) < 3:
            return 0.0
        twice = 0.0
        for one, two in zip(self.corners, self.corners[1:] + self.corners[:1]):
            twice += one[0] * two[1] - two[0] * one[1]
        return abs(twice) / 2.0

    def described(self) -> dict:
        said = super().described()
        said.update({"corners": [[round(float(c[0]), 2), round(float(c[1]), 2)]
                                 for c in self.corners],
                     "areaM2": round(self.area_m2(), 1)})
        return said


class World:
    """Everything a place was arranged with, and what it does to a vehicle."""

    def __init__(self, document: dict | None = None) -> None:
        self.things: list[Thing] = []
        self.version = ""
        self.struck = 0
        if isinstance(document, dict):
            for said in document.get("things") or []:
                if isinstance(said, dict):
                    self.things.append(Thing.of(said))

    def __len__(self) -> int:
        return len(self.things)

    def of_kind(self, kind: str) -> list[Thing]:
        return [one for one in self.things if one.kind == kind]

    def by_id(self, which: str) -> Thing | None:
        return next((one for one in self.things if one.id == which), None)

    def keep_out(self, position, was, half_width: float):
        """Stop a vehicle that has been driven into something.

        The same two constraints the ground applies: put it back where it was
        allowed to be, and take away the velocity that carried it out. A thing
        in the water is not a wall to slide along and not a spring to bounce
        off; it is somewhere the vehicle cannot be.

        Answers the position it is allowed to hold and what it struck, or the
        position unchanged and nothing.
        """
        for thing in self.things:
            if not thing.near(position, half_width):
                continue
            self.struck += 1
            return thing.push_out(position, was, half_width), thing
        return position, None

    def regions(self) -> list:
        """The plots drawn on this chart. What a task points at."""
        return [one for one in self.things if isinstance(one, Region)]

    def inside(self, position) -> list:
        """Which drawn plots a point is inside. Empty for most of the sea."""
        return [one for one in self.regions() if one.contains(position)]

    def described(self) -> dict:
        """What is in the water, for the record and for a console."""
        counted: dict[str, int] = {}
        for one in self.things:
            counted[one.kind] = counted.get(one.kind, 0) + 1
        return {"things": len(self.things), "of": counted,
                "struck": self.struck,
                "layoutVersion": self.version or None,
                "each": [one.described() for one in self.things[:40]]}
