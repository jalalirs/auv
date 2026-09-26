"""A multibeam echosounder: a swath of soundings under the vehicle.

The forward-looking sonar in `sonar.py` exists so a controller can avoid
something nobody told it about. This is the other instrument, and it is the
one the survey programmes actually buy: a fan pointed *down*, across the
track, returning a depth for each beam. Fly a line and you have a ribbon of
bathymetry; fly a grid of lines and you have a chart.

**Why it is a second class and not a flag on the first.** They answer
different questions and fail differently. A forward-looking sonar wants the
nearest return in each direction and treats the bottom as an obstacle; a
multibeam wants *the bottom* in each direction, at a known angle, with the
sounding's position on the Earth attached — and a return off a coral head is
a sounding, not a thing to steer around. Sharing the ray walk is worth it;
sharing the interpretation would be wrong.

**What is modelled, and what is not.** The geometry: where each beam leaves
the transducer, where it meets the ground, how deep that is and how far
across the track. The errors that decide whether a survey is any good: a
sounding's depth error grows with the angle off nadir, because a beam at
sixty degrees travels further through water whose sound speed nobody knows
exactly and lands on ground it hits at a glancing angle. And the refusal at
the edge: past a stated angle the outer beams are dropped, which is what a
surveyor does with them anyway.

What is not modelled is the acoustics — no beam pattern, no sidelobes, no
absorption, no sound-speed profile. Those decide whether a real instrument
gets a return at all. What is here decides whether a *survey plan* is any
good: how wide a swath you get from an altitude, how the lines have to
overlap, and how the error grows at the edge. That is the question a
campaign asks, and it is answerable from geometry.
"""

from __future__ import annotations

import math

import numpy as np

# How many beams across the swath. Real instruments run from 256 to over a
# thousand; 256 is enough that the across-track spacing is finer than the
# heightfields this platform carries, and casting a thousand rays a ping
# would cost more than it tells anybody.
BEAMS = 256

# How often it pings. A shallow-water multibeam runs fast — the limit is the
# two-way travel time — but a survey is flown at a metre or two a second and
# ten a second already puts the pings closer together than the beams are.
PINGS_PER_SECOND = 10.0

# How far off nadir the outer beams are kept. A swath is usually quoted as
# ±60°, which is 3.5 times the altitude wide, and beyond that the soundings
# are bad enough that a surveyor throws them away.
HALF_SWATH_DEG = 60.0

# How a sounding's depth error grows with the angle off nadir.
#
# Flat: a fixed error would say a beam at sixty degrees is as good as one
# straight down, which is the single thing everybody who has used one of
# these knows to be false. The growth is taken as 1/cos — the extra path
# through water whose sound speed is not exactly known — which is the
# first-order term and is honest about being only that.
DEPTH_NOISE_M = 0.02
ACROSS_NOISE_M = 0.05


class Multibeam:
    """A downward-looking swath, as the vehicle's package describes it."""

    def __init__(self, said: dict | None = None, seed: int = 0) -> None:
        said = dict(said or {})
        self.beams = int(said.get("beams", BEAMS))
        self.half_swath = math.radians(float(said.get("halfSwathDeg", HALF_SWATH_DEG)))
        at = said.get("rangeM") or [0.5, 200.0]
        self.near = float(at[0])
        self.far = float(at[1])
        self.at = np.array(said.get("position") or [0.0, 0.0, 0.0], dtype=float)
        self.every = 1.0 / float(said.get("pingsPerSecond", PINGS_PER_SECOND))
        self.depth_noise = float(said.get("depthNoiseM", DEPTH_NOISE_M))
        self.across_noise = float(said.get("acrossNoiseM", ACROSS_NOISE_M))
        self._draw = np.random.RandomState(seed % (2 ** 32))

        self.last_t: float | None = None
        self.pings = 0
        self.soundings = 0
        self.dropped = 0
        self.last: dict | None = None

    def angles(self) -> np.ndarray:
        """Where each beam points, in radians off straight down, port to starboard."""
        if self.beams == 1:
            return np.zeros(1)
        return np.linspace(-self.half_swath, self.half_swath, self.beams)

    def due(self, t: float) -> bool:
        return self.last_t is None or (t - self.last_t) >= self.every

    def swath_width(self, altitude: float) -> float:
        """How wide a strip this covers from a given height off the bottom.

        The number a survey plan is made of: lines this far apart with no
        overlap leave gaps the moment the vehicle rolls, which is why a real
        plan overlaps them.
        """
        return 2.0 * altitude * math.tan(self.half_swath)

    def ping(self, t: float, position, rotation, seabed=None) -> dict:
        """One swath: a sounding per beam, in the world's own coordinates.

        Cast from where the transducer is on the hull and swept across the
        hull's own athwartships axis, so a vehicle that is rolled is surveying
        a strip that is rolled with it — which is exactly the error a survey
        has to correct for and the reason attitude is logged beside every
        ping.
        """
        from sonar import _ground

        self.last_t = t
        self.pings += 1
        origin = np.asarray(position, dtype=float) + np.asarray(rotation) @ self.at
        rotation = np.asarray(rotation, dtype=float)
        down = -rotation[:, 2]              # the hull's own down
        across = rotation[:, 1]             # starboard

        xs, ys, depths, angles, offsets = [], [], [], [], []
        for angle in self.angles():
            way = math.cos(angle) * down + math.sin(angle) * across
            way = way / max(1e-9, float(np.linalg.norm(way)))
            far = _ground(origin, way, self.far, seabed) if seabed is not None else None
            if far is None or far < self.near:
                self.dropped += 1
                continue
            where = origin + way * far
            # The error a surveyor lives with: it grows with the angle off
            # nadir, because the beam travels further through water whose
            # sound speed nobody knows exactly and lands on ground it meets
            # at a glancing angle.
            worse = 1.0 / max(0.2, math.cos(angle))
            depth = float(-where[2]) + float(self._draw.normal(0.0, self.depth_noise * worse))
            sideways = float(self._draw.normal(0.0, self.across_noise * worse))
            xs.append(float(where[0]) + sideways * float(across[0]))
            ys.append(float(where[1]) + sideways * float(across[1]))
            depths.append(depth)
            angles.append(float(angle))
            offsets.append(float(far * math.sin(angle)))
            self.soundings += 1

        self.last = {"t": round(float(t), 3), "beams": len(depths),
                     "x": xs, "y": ys, "depthM": depths,
                     "angleRad": angles, "acrossM": offsets}
        return self.last

    def said(self) -> dict:
        """What this instrument is and what it has done, for the record."""
        return {"beams": self.beams,
                "halfSwathDeg": round(math.degrees(self.half_swath), 1),
                "pingsPerSecond": round(1.0 / self.every, 2),
                "rangeM": [self.near, self.far],
                "depthNoiseM": self.depth_noise,
                "pings": self.pings, "soundings": self.soundings,
                "dropped": self.dropped,
                "noiseGrowsWith": "1/cos of the angle off nadir"}
