"""The sea surface, from a significant wave height and a period.

The waves were four trains somebody chose: fixed lengths, fixed heights, always
the same sea. That is enough to stop the surface being a sheet of glass and it
is not a sea state — it cannot be told that today is half a metre and Thursday
is two, and it cannot be driven by a measurement.

This is a spectrum instead. JONSWAP, which is the North Sea fetch-limited form
and the one every offshore engineer uses, sampled into a set of components with
random phases and a directional spread. Given a significant wave height and a
peak period — the two numbers a wave buoy actually reports, and the two
`asMeasured` now takes off a Sofar Spotter — it produces a surface whose own
significant height is the one that was asked for.

**Why it matters beyond the picture.** A surface vehicle in a sea state is a
vehicle that pitches, and a survey flown from one is only as good as that. A
launch and a recovery happen at the surface. And a vehicle working in the top
half-wavelength feels the orbital motion of the waves above it, which is a real
force and the reason shallow work stops when the weather comes up.
"""

from __future__ import annotations

import math

import numpy as np

# The peak enhancement factor, and the widths either side of the peak. These
# are JONSWAP's own constants, fitted to the North Sea and used everywhere.
GAMMA = 3.3
SIGMA_BELOW = 0.07
SIGMA_ABOVE = 0.09
GRAVITY = 9.81

# How many components to sample the spectrum with. Enough that the sea does not
# repeat visibly over a dive; few enough that the sum is cheap per vertex.
COMPONENTS = 24
# How far off the mean heading the energy spreads. A real sea is not a set of
# parallel crests: cos-squared spreading is the standard first approximation.
SPREAD_DEG = 30.0


def jonswap(frequency: float, peak: float) -> float:
    """Energy density at a frequency, for a sea peaking at `peak` hertz."""
    if frequency <= 0.0:
        return 0.0
    sigma = SIGMA_BELOW if frequency <= peak else SIGMA_ABOVE
    r = math.exp(-((frequency - peak) ** 2) / (2.0 * (sigma * peak) ** 2))
    shape = (GRAVITY ** 2) / ((2.0 * math.pi) ** 4 * frequency ** 5)
    return shape * math.exp(-1.25 * (peak / frequency) ** 4) * (GAMMA ** r)


class SeaState:
    """A sea of a stated height and period, as waves that can be summed."""

    def __init__(self, significant_height_m: float = 0.0,
                 peak_period_s: float = 6.0, heading_deg: float = 0.0,
                 seed: int = 0) -> None:
        self.height = max(0.0, float(significant_height_m))
        self.period = max(1.0, float(peak_period_s))
        self.heading = math.radians(float(heading_deg))
        self.waves: list[tuple[float, float, float, float]] = []
        if self.height <= 0.0:
            return

        draw = np.random.RandomState(seed % (2 ** 32))
        peak = 1.0 / self.period
        # Sampled from a third of the peak frequency to three times it, which
        # holds effectively all of a JONSWAP sea's energy.
        lows = np.linspace(peak / 3.0, peak * 3.0, COMPONENTS + 1)
        amplitudes, ws, dirs = [], [], []
        for low, high in zip(lows, lows[1:]):
            middle = 0.5 * (low + high)
            # Energy in this slice, as an amplitude: a = sqrt(2 S df).
            amplitudes.append(math.sqrt(max(0.0, 2.0 * jonswap(middle, peak) * (high - low))))
            ws.append(2.0 * math.pi * middle)
            # cos-squared spreading about the mean heading.
            spread = math.radians(SPREAD_DEG) * float(draw.normal(0.0, 0.5))
            dirs.append(self.heading + max(-math.pi / 2, min(math.pi / 2, spread)))

        # Scaled so the sea that comes out is the sea that was asked for.
        # Significant height is four times the root of the variance, and the
        # variance of a sum of sine components is half the sum of the squares
        # of their amplitudes.
        variance = 0.5 * sum(a * a for a in amplitudes)
        scale = 1.0 if variance <= 0.0 else self.height / (4.0 * math.sqrt(variance))
        for a, w, d in zip(amplitudes, ws, dirs):
            phase = float(draw.random_sample()) * 2.0 * math.pi
            self.waves.append((a * scale, w, d, phase))

    @property
    def flat(self) -> bool:
        return not self.waves

    def height_at(self, x: float, y: float, seconds: float = 0.0) -> float:
        """How high the water stands above its mean level, here and now."""
        total = 0.0
        for amplitude, w, heading, phase in self.waves:
            # Deep water: k = w² / g, so each component travels at its own
            # speed and the sea disperses rather than moving as one texture.
            k = w * w / GRAVITY
            total += amplitude * math.sin(
                k * (x * math.cos(heading) + y * math.sin(heading)) - w * seconds + phase)
        return total

    def orbital_at(self, x: float, y: float, depth: float, seconds: float = 0.0):
        """The water's own motion under the waves, at a depth below the surface.

        Orbital velocity dies as exp(-k z), so it is the short waves that stop
        mattering first and a vehicle only feels the sea in the top half of a
        wavelength. This is why shallow work stops when the weather comes up
        and why a dive at forty metres does not care.
        """
        u = v = w_vel = 0.0
        z = max(0.0, float(depth))
        for amplitude, w, heading, phase in self.waves:
            k = w * w / GRAVITY
            decay = math.exp(-k * z)
            if decay < 1e-4:
                continue
            phi = k * (x * math.cos(heading) + y * math.sin(heading)) - w * seconds + phase
            speed = amplitude * w * decay
            u += speed * math.cos(phi) * math.cos(heading)
            v += speed * math.cos(phi) * math.sin(heading)
            w_vel += speed * math.sin(phi)
        return np.array([u, v, w_vel], dtype=float)

    def said(self) -> dict:
        return {"significantHeightM": round(self.height, 2),
                "peakPeriodS": round(self.period, 1),
                "headingDeg": round(math.degrees(self.heading), 1),
                "components": len(self.waves)}
