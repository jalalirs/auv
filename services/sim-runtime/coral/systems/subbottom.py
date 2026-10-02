"""A sub-bottom profiler: what is under the seabed, layer by layer, along the track.

Reads    the vehicle (the towfish), the place, the clock
Writes   subbottom: the section, a trace a ping

A chirp of low sound (1–10 kHz on the EdgeTech 2300) goes straight down,
through the water, into the seabed and on through what lies under it. Every
boundary between two kinds of ground sends some of it back — how much is set
by how different they are acoustically (the reflection coefficient from their
impedances, density times sound speed) — and every metre of sediment it goes
through takes some of it away (Hamilton: attenuation proportional to
frequency, a property of each kind of ground). The traces, stacked along the
track, are the section a geologist reads: the seabed, the layers under it, and
where they end.

What is under the seabed is the place's to say, as `subsurface` in its record:

    "subsurface": [{"material": "sand", "thicknessM": 2.0},
                   {"material": "silt", "thicknessM": 6.0},
                   {"material": "limestone"}]

and a place that says nothing gets two metres of sand over six of silt over
limestone, assumed and said so — a carbonate shelf's usual column. The
impedances and attenuations are Hamilton's (1980) and the textbook values for
water and limestone; the resolution is the instrument's (10–30 cm) and the
penetration follows from the attenuation (EdgeTech: 20 m into coarse sand,
200 m into clay).
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

# kind: (density kg/m3, sound speed m/s, attenuation dB / m / kHz)
GROUND = {
    "water": (1025.0, 1500.0, 0.0),
    "sand": (2000.0, 1750.0, 0.5),
    "silt": (1800.0, 1600.0, 0.2),
    "clay": (1500.0, 1500.0, 0.1),
    "limestone": (2400.0, 3000.0, 0.05),
}
ASSUMED = [{"material": "sand", "thicknessM": 2.0}, {"material": "silt", "thicknessM": 6.0},
           {"material": "limestone"}]


class SubBottom:
    def __init__(self) -> None:
        self.fitted = False
        self.centre_khz = 5.0
        self.resolution_m = 0.2
        self.below_m = 40.0              # how deep under the seabed the section goes
        self.bins = 400
        self.column = list(ASSUMED)
        self.from_ = ""
        self.traces: list[np.ndarray] = []

    def set_for(self, said: dict, subsurface=None) -> None:
        band = said.get("bandkHz") or [1, 10]
        self.centre_khz = 0.5 * (float(band[0]) + float(band[1]))
        reso = said.get("resolutionM") or [0.1, 0.3]
        self.resolution_m = float(np.mean(reso))
        self.column = list(subsurface) if subsurface else list(ASSUMED)
        self.from_ = ("the place's record of what lies under it" if subsurface else
                      "assumed: two metres of sand over six of silt over limestone, a carbonate shelf's column")
        self.fitted = True

    def image(self) -> np.ndarray:
        """The section, a column a ping, the seabed at the top, 0..255, in
        decibels over fifty of range — as a profiler's record is shown, because
        a layer forty decibels under the seabed's echo is still a layer."""
        if not self.traces:
            return np.zeros((self.bins, 1), dtype=np.uint8)
        a = np.array(self.traces).T
        top = float(a.max()) if a.size else 1.0
        db = 20.0 * np.log10(np.maximum(a, 1e-12) / max(top, 1e-12))
        return np.clip((db + 50.0) / 50.0 * 255.0, 0, 255).astype(np.uint8)

    def said(self) -> dict:
        return {"centrekHz": self.centre_khz, "traces": len(self.traces), "belowM": self.below_m,
                "column": self.column, "from": self.from_}


def trace(column, centre_khz: float, resolution_m: float, below_m: float, bins: int, rng,
          grain: float = 0.003) -> np.ndarray:
    """One ping's echo by depth under the seabed: a spike at each boundary,
    as strong as its reflection coefficient and what the layers above have
    left of the sound, spread by the instrument's resolution."""
    out = np.zeros(bins)
    depth = 0.0
    above = GROUND["water"]
    left = 1.0                                   # share of the sound still going down
    z = np.linspace(0.0, below_m, bins)
    for layer in column:
        kind = GROUND.get(str(layer.get("material")), GROUND["sand"])
        z1, z2 = above[0] * above[1], kind[0] * kind[1]
        r = (z2 - z1) / (z2 + z1)
        # The boundary: what comes back from it, both ways through what is above.
        strength = abs(r) * left
        out += strength * np.exp(-0.5 * ((z - depth) / (0.5 * resolution_m)) ** 2)
        # Through it, and on down through the layer.
        left *= (1.0 - r * r)
        thick = float(layer.get("thicknessM", below_m - depth))
        db = kind[2] * centre_khz * thick * 2.0            # there and back
        left *= 10.0 ** (-db / 20.0)
        depth += thick
        above = kind
        if depth >= below_m:
            break
    # The grain of a real record: scattering inside the layers, fainter as the
    # sound is spent.
    if grain > 0.0:
        out += grain * rng.exponential(1.0, bins) * np.interp(z, [0.0, below_m], [1.0, 0.1])
    return out


class SubBottomSystem(System):
    name = "subbottom"
    reads = ("vehicle", "place", "clock")
    writes = ("subbottom",)
    every = 0.25

    def __init__(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed + 31)

    def step(self, world) -> None:
        sb = world.subbottom
        if not sb.fitted:
            return
        v, place = world.vehicle, world.place
        floor = place.bottoms(v.position[None, :])[0]
        if not np.isfinite(floor):
            return
        sb.traces.append(trace(sb.column, sb.centre_khz, sb.resolution_m, sb.below_m, sb.bins, self.rng))
