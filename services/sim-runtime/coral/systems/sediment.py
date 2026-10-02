"""Sand and silt the thrusters lift, the water carries, and the bed takes back.

Reads    the wash, the water, the vehicle, the place, the coral, the clock
Writes   sediment: the grains in the water, what has settled where, and how
         far the camera can see through them
Every    a twentieth of a second of simulated time

A vehicle working low over sand blows it up. That is the thing every ROV
pilot over a soft bottom knows, and what it costs is the picture: the camera
sees less, and the vehicle's own record of the reef is the cloud it made.
Here it is the standard chain, each step a published relation:

  **When the bed moves.** The wash's speed just over the bed, as a shear
  stress τ = ρ C_f u² (C_f = 0.005, assumed), against each grain size's
  critical stress from the Soulsby–Whitehouse Shields curve (for 0.25 mm sand
  about 0.16 Pa; for silt about 0.07).
  **How much.** Past it, the bed erodes at E = M (τ/τ_c − 1), M = 5 × 10⁻⁴
  kg m⁻² s⁻¹ (Partheniades' form; M is assumed — it is the number that varies
  most from one bottom to the next).
  **Where it goes.** As parcels of grains carried by the water's own motion
  and the wash, mixed by the jet's turbulence, and falling at the grain's
  settling speed (Ferguson & Church 2004: about 3 cm/s for the sand, a third
  of a millimetre a second for the silt — so the sand falls back in a second
  and the silt hangs for minutes, which is what a real plume does).
  **What it costs the camera.** The beam attenuation it adds, per gram per
  cubic metre (assumed: 0.3 m²/g for silt, 0.01 for sand), on top of the
  water's own; horizontal visibility is about 4.8 over the attenuation
  (Zaneveld & Pegau 2003).
  **What it does to the coral.** What settles on a colony, in milligrams per
  square centimetre, against the thresholds the coral literature gives: harm
  begins about 10 mg cm⁻² a day and is severe past 50 (Erftemeijer et al. 2012;
  Tuttle & Donahue 2022).

The bed here is a reef tank's: aragonite sand with a tenth of fines (assumed).
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

RHO = 1025.0
GRAIN_RHO = 2650.0
NU = 1.05e-6               # kinematic viscosity of seawater, m²/s
G = 9.80665
FRICTION_C = 0.005         # bed friction coefficient, assumed
ERODES_M = 5e-4            # kg m⁻² s⁻¹, assumed
PARCEL_KG = 2e-6           # two milligrams a parcel
MOST_PARCELS = 6000


def settling(d: float) -> float:
    """Ferguson & Church (2004) settling speed of a natural grain, m/s."""
    r = (GRAIN_RHO - RHO) / RHO
    return r * G * d * d / (18.0 * NU + math.sqrt(0.75 * 1.0 * r * G * d ** 3))


def critical(d: float) -> float:
    """Soulsby–Whitehouse critical shear stress for a grain size, Pa."""
    r = (GRAIN_RHO - RHO) / RHO
    dstar = d * (G * r / NU ** 2) ** (1.0 / 3.0)
    shields = 0.30 / (1.0 + 1.2 * dstar) + 0.055 * (1.0 - math.exp(-0.020 * dstar))
    return shields * (GRAIN_RHO - RHO) * G * d


class Grain:
    def __init__(self, name, d, share, attenuation):
        self.name, self.d, self.share, self.attenuation = name, d, share, attenuation
        self.falls = settling(d)
        self.critical = critical(d)


# The bed's grains: a reef tank's aragonite sand and the fines in it.
GRAINS = [Grain("sand", 0.25e-3, 0.9, 0.01), Grain("silt", 0.03e-3, 0.1, 0.3)]


def wash_origin_over(wash, points) -> np.ndarray:
    """Where, over the bed, the nearest jet came from: what a wall jet
    spreads out from."""
    if not len(wash.origin):
        return np.zeros((len(points), 2))
    d = np.linalg.norm(points[:, None, :2] - wash.origin[None, :, :2], axis=2)
    return wash.origin[np.argmin(d, axis=1), :2]


class Sediment:
    def __init__(self) -> None:
        self.at = np.zeros((0, 3))
        self.grain = np.zeros(0, dtype=int)
        self.kg = np.zeros(0)
        self.lifted_kg = 0.0
        self.settled_kg = 0.0
        self.most_in_water = 0
        self.visibility_m = None          # in front of the camera, now
        self.worst_visibility_m = None
        self.on_coral_mg_cm2 = None       # what has settled on each colony
        self.from_ = "nothing yet"

    def said(self) -> dict:
        return {"liftedG": round(self.lifted_kg * 1000.0, 2), "settledG": round(self.settled_kg * 1000.0, 2),
                "inTheWaterG": round(float(self.kg.sum()) * 1000.0, 2), "mostParcels": self.most_in_water,
                "visibilityM": None if self.visibility_m is None else round(self.visibility_m, 2),
                "worstVisibilityM": None if self.worst_visibility_m is None else round(self.worst_visibility_m, 2),
                "worstOnACoralMgCm2": None if self.on_coral_mg_cm2 is None or not len(self.on_coral_mg_cm2)
                else round(float(self.on_coral_mg_cm2.max()), 3),
                "grains": {g.name: {"diameterMm": g.d * 1000, "fallsMs": round(g.falls, 5),
                                    "criticalPa": round(g.critical, 3)} for g in GRAINS},
                "from": self.from_}


class SedimentSystem(System):
    name = "sediment"
    reads = ("wash", "water", "vehicle", "place", "coral", "clock")
    writes = ("sediment",)
    every = 0.05

    # The water's own attenuation, m⁻¹, when nothing is in it: clear coastal
    # water is about this at green light (Jerlov's type I is clearer).
    CLEAR = 0.15
    # How close to the bed a jet is a wall jet.
    WALL_JET_M = 0.04
    # How far round the vehicle the bed is looked at, and how finely.
    LOOKS_M = 0.8
    CELL_M = 0.03

    def __init__(self, seed: int, say) -> None:
        self.rng = np.random.default_rng(seed + 11)
        self.say = say
        self.warned = False

    def step(self, world) -> None:
        sed, wash, water, v, place = world.sediment, world.wash, world.water, world.vehicle, world.place
        dt = self.every
        if sed.from_ == "nothing yet":
            sed.from_ = ("derived: Soulsby–Whitehouse thresholds, Partheniades erosion, Ferguson–Church "
                         "settling, under the vehicle's wash; bed friction, erodibility and the bed's grains "
                         "assumed")
        if place.seabed is not None or place.floor is not None:
            self.lift(sed, wash, v, place, dt)
        if len(sed.kg):
            self.carry(sed, wash, water, place, dt, world.clock.simulated, world.coral)
        sed.most_in_water = max(sed.most_in_water, len(sed.kg))
        self.see(sed, v)

    def lift(self, sed, wash, v, place, dt) -> None:
        """Erode the bed under the wash, as parcels of grains."""
        if not wash.efflux.any():
            return
        n = int(2 * self.LOOKS_M / self.CELL_M)
        line = np.linspace(-self.LOOKS_M, self.LOOKS_M, n)
        gx, gy = np.meshgrid(line + v.position[0], line + v.position[1])
        cells = np.column_stack([gx.ravel(), gy.ravel()])
        bed = place.bottoms(np.column_stack([cells, np.zeros(len(cells))]))
        if place.interior is not None:
            low, high = place.interior
            keep = (cells[:, 0] > low[0]) & (cells[:, 0] < high[0]) & (cells[:, 1] > low[1]) & (cells[:, 1] < high[1])
            cells, bed = cells[keep], bed[keep]
        over = np.column_stack([cells, bed + 0.01])
        u = np.linalg.norm(wash.at(over), axis=1)
        tau = RHO * FRICTION_C * u * u
        area = self.CELL_M * self.CELL_M
        for k, grain in enumerate(GRAINS):
            excess = tau / grain.critical - 1.0
            moving = excess > 0.0
            if not moving.any():
                continue
            kg = ERODES_M * excess[moving] * area * dt * grain.share
            sed.lifted_kg += float(kg.sum())
            # Into parcels: whole ones where there is enough, and the rest by
            # chance, so a little erosion everywhere is still some grains.
            count = np.floor(kg / PARCEL_KG + self.rng.random(len(kg))).astype(int)
            if not count.any():
                continue
            where = np.repeat(over[moving], count, axis=0)
            where[:, :2] += self.rng.uniform(-0.5, 0.5, (len(where), 2)) * self.CELL_M
            sed.at = np.vstack([sed.at, where])
            sed.grain = np.concatenate([sed.grain, np.full(len(where), k)])
            sed.kg = np.concatenate([sed.kg, np.full(len(where), PARCEL_KG)])
        if len(sed.kg) > MOST_PARCELS:
            keep = slice(len(sed.kg) - MOST_PARCELS, None)
            sed.at, sed.grain, sed.kg = sed.at[keep], sed.grain[keep], sed.kg[keep]
            if not self.warned:
                self.warned = True
                self.say("sediment_capped", parcels=MOST_PARCELS,
                         why="more sand in the water than is followed; the oldest is let go")

    def carry(self, sed, wash, water, place, dt, now, coral) -> None:
        """Carried by the water and the wash, mixed, falling; back on the bed
        where it lands."""
        flow = water.flow_at(sed.at, now) + wash.at(sed.at)
        bed = place.bottoms(sed.at)
        # A jet that meets the bed turns along it — a wall jet, spreading out
        # from where it struck — and its turbulence holds grains up: near the
        # bed, what was driving into it goes outwards along it instead, and a
        # share of it lifts (assumed: a sixth, the order of a wall jet's
        # turbulent intensity).
        near = (sed.at[:, 2] - bed) < self.WALL_JET_M
        into = near & (flow[:, 2] < 0.0)
        if into.any():
            out = sed.at[into, :2] - wash_origin_over(wash, sed.at[into])
            out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-6)
            down = -flow[into, 2]
            flow[into, :2] += out * down[:, None]
            flow[into, 2] = down / 6.0
        falls = np.array([GRAINS[k].falls for k in sed.grain])
        # Mixing: a jet stirs as hard as it blows (an eddy diffusivity of a
        # few per cent of speed times its width), and still water barely.
        speed = np.linalg.norm(flow, axis=1)
        spread = np.sqrt(2.0 * (1e-5 + 0.02 * speed * 0.04) * dt)
        sed.at = sed.at + (flow - np.column_stack([np.zeros((len(falls), 2)), falls])) * dt \
            + self.rng.normal(0.0, 1.0, sed.at.shape) * spread[:, None]
        if place.interior is not None:
            low, high = place.interior
            sed.at[:, 0] = np.clip(sed.at[:, 0], low[0], high[0])
            sed.at[:, 1] = np.clip(sed.at[:, 1], low[1], high[1])
        sed.at[:, 2] = np.minimum(sed.at[:, 2], water.level - 0.005)
        bed = place.bottoms(sed.at)
        down = sed.at[:, 2] <= bed
        if down.any():
            sed.settled_kg += float(sed.kg[down].sum())
            self.on_the_coral(sed, coral, sed.at[down], sed.kg[down])
            keep = ~down
            sed.at, sed.grain, sed.kg = sed.at[keep], sed.grain[keep], sed.kg[keep]

    @staticmethod
    def on_the_coral(sed, coral, where, kg) -> None:
        """What lands within a colony's reach settles on it."""
        if coral is None or not len(coral):
            return
        if sed.on_coral_mg_cm2 is None or len(sed.on_coral_mg_cm2) != len(coral):
            sed.on_coral_mg_cm2 = np.zeros(len(coral))
        d = np.linalg.norm(where[:, None, :2] - coral.at[None, :, :2], axis=2)
        landed = d < coral.radius[None, :]
        area_cm2 = math.pi * (coral.radius * 100.0) ** 2
        sed.on_coral_mg_cm2 += (landed * kg[:, None]).sum(axis=0) * 1e6 / area_cm2

    def see(self, sed, v) -> None:
        """How far the camera sees: the attenuation in the water just ahead of
        it, the water's own plus what is hanging there."""
        ahead = v.position + v.rotation @ np.array([0.25, 0.0, 0.0])
        if len(sed.kg):
            near = np.linalg.norm(sed.at - ahead[None, :], axis=1) < 0.25
            volume = 4.0 / 3.0 * math.pi * 0.25 ** 3
            grams = np.array([sed.kg[near & (sed.grain == k)].sum() for k in range(len(GRAINS))]) * 1000.0
            added = sum(g / volume * grain.attenuation for g, grain in zip(grams, GRAINS))
        else:
            added = 0.0
        sed.visibility_m = 4.8 / (self.CLEAR + added)
        sed.worst_visibility_m = (sed.visibility_m if sed.worst_visibility_m is None
                                  else min(sed.worst_visibility_m, sed.visibility_m))
