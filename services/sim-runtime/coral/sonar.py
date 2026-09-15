"""What the vehicle can see that nobody told it about.

An imaging sonar has been declared in the BlueROV2's package since the
beginning — a hundred and thirty degrees wide, twenty tall, half a metre to
ten — and has returned nothing this whole time, because there was nothing in
the world to return off. There is now.

**Ranges, not an image.** A real forward-looking sonar returns a fan of beams
and an intensity along each; what a pilot sees is that fan drawn as a picture,
and what a controller acts on is the range to the nearest thing in each
direction. Rendering the picture is a rendering problem and belongs to the
application that has a renderer; the ranges are the physics, and they are what
makes "avoid something you were not told about" true rather than decorative.

**What it can see.** Anything somebody put in the water, and the seabed. Not
the coral, which is a texture rather than a thing, and not the water itself:
this is a geometric sonar and it does not model reverberation, multipath, or
the way a wall at a glancing angle returns almost nothing. Those are real and
they are what makes sonar hard; what is modelled here is the part a collision
avoider needs, plus enough noise and dropout that a controller which trusts
every single ping is a controller that will be surprised at sea.

**Why the beams are cheap.** A ray against a handful of cylinders and a
heightfield, sixty-four times, a few times a second. Not every physics step:
a sonar that pinged at two hundred hertz would be a sonar that does not exist,
and the rate it really runs at is part of what a controller has to live with.
"""

from __future__ import annotations

import math

import numpy as np

# How many beams across the fan. Sixty-four is about what a small multibeam
# gives and is fine enough that a mooring block is several beams wide at the
# range it matters.
BEAMS = 64

# How often it pings, in hertz. A forward-looking imaging sonar runs at a few
# frames a second; a controller that expected a fresh picture every step would
# be a controller written against a machine that does not exist.
PINGS_PER_SECOND = 5.0


class Sonar:
    """A forward-looking fan, as the vehicle's package describes it."""

    def __init__(self, said: dict | None = None, seed: int = 0) -> None:
        said = dict(said or {})
        at = said.get("rangeM") or [0.5, 10.0]
        self.near = float(at[0])
        self.far = float(at[1])
        self.wide = math.radians(float(said.get("horizontalFovDeg", 130.0)))
        self.tall = math.radians(float(said.get("verticalFovDeg", 20.0)))
        self.at = np.array(said.get("position") or [0.0, 0.0, 0.0], dtype=float)
        self.beams = int(said.get("beams", BEAMS))
        self.every = 1.0 / float(said.get("pingsPerSecond", PINGS_PER_SECOND))

        # A sonar that returned a clean range every time would be a sonar
        # nobody has ever owned. Both drawn once and held, so two runs of one
        # seed ping the same.
        draw = np.random.RandomState(seed % (2 ** 32))
        self.noise_m = float(said.get("rangeNoiseM", 0.05))
        self.misses = float(said.get("missesShare", 0.04))
        self._draw = draw

        self.last_t: float | None = None
        self.ranges = np.full(self.beams, np.nan)
        self.pings = 0

    def spread(self) -> float:
        """How wide a beam is, in radians.

        Taken as the angle between beams, which is what a fan of this many
        across this arc actually resolves. It matters because a beam is a cone
        and not a line: a mooring riser is five millimetres thick and two beams
        at five metres are eighteen centimetres apart, so a model that cast
        rays would have the sonar miss the cable nine times in ten — which is
        not what a sonar does and is the opposite of the point of having one.
        """
        if self.beams < 2:
            return self.wide
        return self.wide / (self.beams - 1)

    def bearings(self) -> np.ndarray:
        """Where each beam points, in radians off the nose, port to starboard."""
        if self.beams == 1:
            return np.zeros(1)
        return np.linspace(-self.wide / 2.0, self.wide / 2.0, self.beams)

    def due(self, t: float) -> bool:
        return self.last_t is None or (t - self.last_t) >= self.every

    def ping(self, t: float, position, rotation, world=None, seabed=None) -> np.ndarray:
        """One sweep of the fan: the range along each beam, or NaN for nothing.

        The beams are cast from where the sonar is on the hull and along where
        the hull is pointing, because a sonar bolted to the front of a vehicle
        that is pitched down is looking at the bottom.
        """
        self.last_t = t
        self.pings += 1
        rotation = np.asarray(rotation, dtype=float)
        origin = np.asarray(position, dtype=float) + rotation @ self.at

        out = np.full(self.beams, np.nan)
        for i, bearing in enumerate(self.bearings()):
            way = rotation @ np.array([math.cos(bearing), math.sin(bearing), 0.0])
            far = self.far
            if world is not None:
                for thing in world.things:
                    hit = _hit(thing, origin, way, far, self.spread())
                    if hit is not None and hit < far:
                        far = hit
            if seabed is not None:
                hit = _ground(origin, way, self.far, seabed)
                if hit is not None and hit < far:
                    far = hit
            if far >= self.far:
                continue                      # nothing out there
            if far < self.near:
                continue                      # inside the blanking range: unseen
            if self._draw.random_sample() < self.misses:
                continue                      # a beam that did not come back
            out[i] = far + self._draw.normal(0.0, self.noise_m)
        self.ranges = out
        return out

    def nearest(self):
        """The closest return and where it is, or nothing.

        What a collision avoider actually asks. The bearing is off the nose,
        positive to starboard, so "turn away from it" is a sign.
        """
        if not np.any(np.isfinite(self.ranges)):
            return None
        at = int(np.nanargmin(self.ranges))
        return {"rangeM": float(self.ranges[at]),
                "bearingRad": float(self.bearings()[at]),
                "beam": at}

    def fan(self) -> dict:
        """The whole sweep, for a controller that wants to find a gap.

        Steering on the nearest return alone cannot avoid anything dead ahead:
        the closest beam flips between the two either side of centre as the
        noise moves, and the vehicle is told to turn first one way and then the
        other while it drives into the thing.
        """
        return {"bearingsRad": self.bearings(), "rangesM": self.ranges}

    def said(self) -> dict:
        near = self.nearest()
        seen = int(np.count_nonzero(np.isfinite(self.ranges)))
        return {"beams": self.beams, "rangeM": [self.near, self.far],
                "fovDeg": round(math.degrees(self.wide), 1),
                "pings": self.pings, "returns": seen,
                "nearestM": None if near is None else round(near["rangeM"], 2),
                "nearestBearingDeg": None if near is None
                else round(math.degrees(near["bearingRad"]), 1)}


# ── what a beam can hit ──────────────────────────────────────────────────────

def _hit(thing, origin: np.ndarray, way: np.ndarray, far: float, spread: float = 0.0):
    """Where a beam meets one thing, or nothing.

    Cylinders for what stands at a point, a run of capsules for what spans
    between two, and nothing at all for a plot drawn on a chart — a boundary
    is not a thing that returns sound.
    """
    curve = getattr(thing, "curve", None)
    if curve is not None:
        best = None
        radius = float(getattr(thing, "radius", 0.05))
        for a, b in zip(curve, curve[1:]):
            at = _segment(origin, way, np.asarray(a), np.asarray(b), radius, far, spread)
            if at is not None and (best is None or at < best):
                best = at
        return best
    at = getattr(thing, "at", None)
    if at is None:
        return None                       # a plot on the chart returns nothing
    return _cylinder(origin, way, np.asarray(at), float(thing.radius),
                     float(thing.low), float(thing.high), far, spread)


def _cylinder(origin, way, at, radius: float, low: float, high: float, far: float,
              spread: float = 0.0):
    """Where a beam meets an upright cylinder, as a distance along the beam."""
    # In the horizontal plane it is a circle; the vertical extent is a check.
    d = np.array([way[0], way[1]])
    f = np.array([origin[0] - at[0], origin[1] - at[1]])
    # Widened by how far the beam has spread by the time it gets there. A
    # marker post is two hundred millimetres across and the beams are eighteen
    # centimetres apart at five metres: a ray would walk straight past it.
    radius = radius + 0.5 * spread * float(np.linalg.norm(f))
    a = float(d @ d)
    if a < 1e-12:
        return None
    b = 2.0 * float(f @ d)
    c = float(f @ f) - radius * radius
    under = b * b - 4 * a * c
    if under < 0.0:
        return None
    root = math.sqrt(under)
    for t in sorted(((-b - root) / (2 * a), (-b + root) / (2 * a))):
        if t <= 0.0 or t > far:
            continue
        z = float(origin[2] + way[2] * t)
        if low <= z <= high:
            return float(t)
    return None


def _segment(origin, way, a, b, radius: float, far: float, spread: float = 0.0):
    """Where a beam meets a capsule between two points.

    Not exact: the closest approach between the beam and the segment, taken as
    a hit when it is inside the radius and the range read off there. A cable is
    a few millimetres thick and a sonar beam is degrees wide — being exact
    about which millimetre it grazed would be precision the instrument does not
    have.
    """
    u = b - a
    w0 = origin - a
    A = float(way @ way)
    B = float(way @ u)
    C = float(u @ u)
    D = float(way @ w0)
    E = float(u @ w0)
    under = A * C - B * B
    if abs(under) < 1e-12:
        t = -D / A if A > 1e-12 else 0.0
        s = 0.0
    else:
        t = (B * E - C * D) / under
        s = (A * E - B * D) / under
    s = max(0.0, min(1.0, s))
    t = float((np.asarray(a) + u * s - origin) @ way / A)
    if t <= 0.0 or t > far:
        return None
    apart = float(np.linalg.norm(origin + way * t - (a + u * s)))
    return t if apart <= radius + 0.5 * spread * t else None


def _ground(origin, way, far: float, seabed):
    """Where a beam meets the bottom, by walking along it.

    A heightfield has no closed form to intersect against, so the beam is
    walked until it is under the ground and the crossing is bisected. Coarse on
    purpose: half a metre of step and eight bisections is centimetres, which is
    finer than the instrument.
    """
    step = 0.5
    was = float(origin[2] - seabed.under(float(origin[0]), float(origin[1])))
    t = step
    while t <= far:
        where = origin + way * t
        above = float(where[2] - seabed.under(float(where[0]), float(where[1])))
        if above <= 0.0 < was or (above <= 0.0 and was <= 0.0):
            low, high = t - step, t
            for _ in range(8):
                mid = 0.5 * (low + high)
                where = origin + way * mid
                if float(where[2] - seabed.under(float(where[0]), float(where[1]))) <= 0.0:
                    high = mid
                else:
                    low = mid
            return float(high)
        was = above
        t += step
    return None
