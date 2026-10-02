"""Side-scan sonar: the waterfall a towfish draws of the seabed either side of it.

Reads    the vehicle (the towfish), the place, the clock
Writes   sidescan: the waterfall, a row a ping

A side-scan sonar sends a fan of sound out sideways from each side of the
fish — thin along the track, wide downwards — and records how loud the echo
is against time, which is range. Pinged as the fish moves, the rows stack into
an image of the seabed: bright where the bottom faces the fish, dark where it
faces away, black in the shadow behind anything standing up. The shadows are
what a side-scan picture is read by, which is why they are computed rather
than painted.

Each ping, each side:

  **Where the sound lands.** Across the track, the ground is sampled from
  under the fish out to the range; a point is heard only if nothing between
  it and the fish stands higher in the way (the horizon test), and only
  within the vertical beam — 50 degrees wide, tilted down 26 (EdgeTech 2300).
  **How loud.** Lambert's law, the backscatter of a rough bottom: as the
  square of the cosine of the angle the sound meets it at, with a speckle
  that every real record has. Spreading and absorption are taken as already
  corrected (time-varied gain), as a survey record is.
  **Where it goes in the row.** By slant range: the time the echo took. The
  first return is the bottom straight below, and everything before it is the
  water column, dark.

The frequency sets the range (EdgeTech 2300: 120 kHz 500 m a side, 410 kHz
200 m, 850 kHz 75 m) and the across-track resolution (6.5 cm, 1.8 cm, 1 cm).
The ping rate is what the range allows — sound has to get there and back.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

SOUND = 1500.0


class SideScan:
    def __init__(self) -> None:
        self.fitted = False
        self.frequency_khz = 0.0
        self.range_m = 0.0
        self.bins = 512
        self.rows: list[np.ndarray] = []
        self.track: list[tuple[float, float, float]] = []
        self.altitude: list[float] = []
        self.from_ = ""

    def set_for(self, said: dict, frequency_khz: float | None = None) -> None:
        """From the sensor's entry in the vehicle package."""
        ranges = {float(k): float(v) for k, v in (said.get("rangeMBykHz") or {}).items()}
        f = float(frequency_khz or said.get("frequencykHz") or (sorted(ranges)[len(ranges) // 2] if ranges else 410.0))
        self.frequency_khz = f
        self.range_m = float(said.get("rangeM") or ranges.get(f, 100.0))
        self.bins = int(said.get("binsPerSide", 512))
        self.vertical_deg = float(said.get("verticalBeamDeg", 50.0))
        self.depression_deg = float(said.get("depressionDeg", 26.0))
        self.fitted = True
        self.from_ = str(said.get("note") or "the vehicle package")

    def image(self) -> np.ndarray:
        """The waterfall, port on the left, newest ping at the bottom, 0..255.

        With angle-varying gain, as survey software shows a record: each range
        bin divided by its mean over the whole run, so the far range — where
        the sound meets the bottom at a grazing angle and comes back weak —
        reads as bottom rather than as black, and what stands out is what is
        different from the bottom round it: a boulder's face, and its shadow."""
        if not self.rows:
            return np.zeros((1, 2 * self.bins), dtype=np.uint8)
        a = np.array(self.rows)
        heard = a > 0
        count = np.maximum(heard.sum(axis=0), 1)
        mean = a.sum(axis=0) / count
        level = np.where(mean > 0, a / np.maximum(mean, 1e-12), 0.0)
        top = np.percentile(level[heard], 99) if heard.any() else 1.0
        return np.clip(level / max(top, 1e-9) * 255.0, 0, 255).astype(np.uint8)

    def said(self) -> dict:
        return {"frequencykHz": self.frequency_khz, "rangeMPerSide": self.range_m, "pings": len(self.rows),
                "binsPerSide": self.bins,
                "altitudeM": None if not self.altitude else
                {"mean": round(float(np.mean(self.altitude)), 2), "min": round(float(np.min(self.altitude)), 2)},
                "from": self.from_}


class SideScanSystem(System):
    name = "sidescan"
    reads = ("vehicle", "place", "clock")
    writes = ("sidescan",)

    def __init__(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed + 23)
        self.next_ping = 0.0

    def step(self, world) -> None:
        scan = world.sidescan
        if not scan.fitted or world.clock.simulated < self.next_ping:
            return
        # As fast as the range allows, and no faster than the record needs.
        self.next_ping = world.clock.simulated + max(2.0 * scan.range_m / SOUND, 1.0 / 15.0)
        v, place = world.vehicle, world.place
        row = [self.side(scan, v, place, sign) for sign in (-1.0, 1.0)]
        scan.rows.append(np.concatenate([row[0][::-1], row[1]]))
        scan.track.append(tuple(float(c) for c in v.position))
        below = place.bottoms(v.position[None, :])[0]
        if np.isfinite(below):
            scan.altitude.append(float(v.position[2] - below))

    def side(self, scan, v, place, sign: float) -> np.ndarray:
        """One side's row: echo strength by slant range."""
        across = v.rotation @ np.array([0.0, sign, 0.0])
        across[2] = 0.0
        across /= max(float(np.linalg.norm(across)), 1e-9)
        n = 4 * scan.bins
        s = np.linspace(0.05, scan.range_m, n)
        ground = v.position[None, :2] + s[:, None] * across[None, :2]
        points = np.column_stack([ground, np.zeros(n)])
        h = place.bottoms(points)
        out = np.zeros(scan.bins)
        if not np.isfinite(h).any():
            return out
        points[:, 2] = h
        rise = h - v.position[2]                        # negative below the fish
        elevation = np.arctan2(rise, s)
        # The horizon: heard only if no nearer ground stands higher in the way.
        lit = elevation >= np.maximum.accumulate(elevation) - 1e-9
        # Within the vertical beam, tilted down.
        depression = -np.degrees(elevation)
        beam = np.exp(-((depression - scan.depression_deg) / (0.5 * scan.vertical_deg)) ** 2)
        # Lambert: the square of the cosine of the angle the sound meets the
        # ground at.
        normal = place.facing(points)
        to_fish = v.position[None, :] - points
        slant = np.linalg.norm(to_fish, axis=1)
        cos_in = np.clip(np.sum(normal * to_fish, axis=1) / np.maximum(slant, 1e-9), 0.0, 1.0)
        strength = cos_in ** 2 * beam * lit * self.rng.exponential(1.0, n)
        bins = np.clip((slant / scan.range_m * scan.bins).astype(int), 0, scan.bins - 1)
        np.maximum.at(out, bins, strength)
        return out
