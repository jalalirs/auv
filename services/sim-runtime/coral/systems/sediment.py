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
  **A dredger** (a "dredger" in the layout) loses sediment at its overflow
  all the time it works: `releaseKgPerS` (default 20, assumed), `finesShare`
  of it silt, at `releaseDepthM` under its keel. The sand falls near it and
  the silt goes where the current takes it. What settles on the colonies is
  judged per day like anything else, so a dive of an hour says what a day of
  dredging at that rate would do.

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
# Carbonate grains, not quartz: the middle of what Prager, Southard &
# Vivoni-Gallart (1996) measured for reef and lagoon sands, 2.50 to 2.77 g/cm³
# (skeletal fragments are lighter than the aragonite they are made of).
GRAIN_RHO = 2730.0
# And they move sooner than the Soulsby–Whitehouse curve says, which is a fit
# to quartz. Prager et al. put four carbonate sands in a flume (ooids, two
# skeletal sands and a patch-reef sand, 0.5 to 0.7 mm): their thresholds were
# 0.70, 0.73, 1.05 and 0.70 of the curve's for the same grains, 0.80 on average.
CARBONATE_THRESHOLD = 0.80
NU = 1.05e-6               # kinematic viscosity of seawater, m²/s
G = 9.80665
FRICTION_C = 0.005         # bed friction coefficient, assumed
ERODES_M = 5e-4            # kg m⁻² s⁻¹, assumed: no erosion rate has been measured for reef carbonate
PARCEL_KG = 2e-6           # two milligrams a parcel
MOST_PARCELS = 60000

# What a dredger loses to the water, when its layout entry does not say.
# A trailing suction hopper dredger overflowing loses fines at its keel, and
# the rate is the number every dredging plume study argues about: tens of
# kilograms a second is the order reported (Becker et al. 2015, J. Environ.
# Manage. 149:282, a review of dredging plume sources). Assumed, and said so.
DREDGE_KG_PER_S = 20.0
DREDGE_FINES = 0.4         # of what it loses, the share that is silt (assumed)
DREDGE_PARCELS_A_STEP = 2
AMBIENT_KH = 0.05          # m²/s, horizontal eddy diffusivity, open water (Okubo 1971 at ~100 m)
AMBIENT_KV = 1e-3          # m²/s, vertical, coastal water (assumed)
# A dredged parcel stands for a puff of the plume, not a lump: half a
# kilogram landing whole on one colony read as 50 mg/cm², every colony one
# parcel touched was "badly smothered", and 13,281 of them were. Each is
# spread over a puff that starts this wide and grows by the same eddy
# diffusivity that walks it (a puff-particle model: de Haan & Rotach 1998).
PUFF_FROM_M = 3.0
PUFF_TALL_FROM_M = 1.0     # and this tall (assumed), growing by AMBIENT_KV


def settling(d: float) -> float:
    """Ferguson & Church (2004) settling speed of a natural grain, m/s."""
    r = (GRAIN_RHO - RHO) / RHO
    return r * G * d * d / (18.0 * NU + math.sqrt(0.75 * 1.0 * r * G * d ** 3))


def critical(d: float) -> float:
    """Critical shear stress for a carbonate grain, Pa: Soulsby–Whitehouse,
    brought down to what Prager et al. (1996) measured for carbonate sands."""
    r = (GRAIN_RHO - RHO) / RHO
    dstar = d * (G * r / NU ** 2) ** (1.0 / 3.0)
    shields = 0.30 / (1.0 + 1.2 * dstar) + 0.055 * (1.0 - math.exp(-0.020 * dstar))
    return CARBONATE_THRESHOLD * shields * (GRAIN_RHO - RHO) * G * d


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


def _puff_m(age):
    """How wide a dredged parcel's puff has grown, m; NaN for a lifted grain."""
    return np.sqrt(PUFF_FROM_M ** 2 + 2.0 * AMBIENT_KH * np.asarray(age, dtype=float))


def hanging(sed, point, now: float, reach: float) -> np.ndarray:
    """What is in the water at `point`, kg/m³ of each grain: the lifted grains
    within `reach`, and every dredged puff as a Gaussian of its own size.

    Counting only parcels within reach, a sonde in the middle of a dredging
    plume read clear water: half-kilogram parcels a few metres apart are
    almost never within thirty centimetres of anything."""
    out = np.zeros(len(GRAINS))
    if not len(sed.kg):
        return out
    born = sed.born if len(getattr(sed, "born", ())) == len(sed.kg) else np.full(len(sed.kg), np.nan)
    puff = np.isfinite(born)
    d = sed.at - np.asarray(point, dtype=float)[None, :]
    close = ~puff & (np.linalg.norm(d, axis=1) < reach)
    if close.any():
        np.add.at(out, sed.grain[close], sed.kg[close] / (4.0 / 3.0 * math.pi * reach ** 3))
    if puff.any():
        age = np.maximum(float(now) - born[puff], 0.0)
        wide = _puff_m(age)
        tall = np.sqrt(PUFF_TALL_FROM_M ** 2 + 2.0 * AMBIENT_KV * age)
        dp = d[puff]
        c = sed.kg[puff] / ((2.0 * math.pi) ** 1.5 * wide ** 2 * tall) * np.exp(
            -(dp[:, 0] ** 2 + dp[:, 1] ** 2) / (2.0 * wide ** 2) - dp[:, 2] ** 2 / (2.0 * tall ** 2))
        np.add.at(out, sed.grain[puff], c)
    return out


class Sediment:
    def __init__(self) -> None:
        self.at = np.zeros((0, 3))
        self.grain = np.zeros(0, dtype=int)
        self.kg = np.zeros(0)
        # When each parcel was let go, for a dredged one; NaN for a grain the
        # vehicle lifted, which lands where it lands.
        self.born = np.zeros(0)
        self.lifted_kg = 0.0
        self.settled_kg = 0.0
        self.most_in_water = 0
        self.visibility_m = None          # in front of the camera, now
        self.worst_visibility_m = None
        self.on_coral_mg_cm2 = None       # what has settled on each colony
        self.from_ = "nothing yet"
        self.dredged_kg = 0.0

    def said(self) -> dict:
        return {"liftedG": round(self.lifted_kg * 1000.0, 2), "settledG": round(self.settled_kg * 1000.0, 2),
                **({"dredgedKg": round(self.dredged_kg, 1)} if getattr(self, "dredged_kg", 0.0) else {}),
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
    reads = ("wash", "flow", "water", "vehicle", "place", "coral", "clock")
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
            sed.from_ = ("derived: Soulsby–Whitehouse thresholds scaled to carbonate sand as Prager et al. "
                         "(1996) measured it, Partheniades erosion, Ferguson–Church settling, under the "
                         "vehicle's wash; bed friction, the erosion rate and the bed's grain sizes assumed")
        if place.seabed is not None or place.floor is not None:
            self.lift(sed, wash, v, place, dt)
        self.dredge(sed, place, water, dt, world.clock.simulated)
        if len(sed.kg):
            self.carry(sed, wash, water, place, dt, world.clock.simulated, world.coral)
        sed.most_in_water = max(sed.most_in_water, len(sed.kg))
        self.see(sed, v, world.clock.simulated)

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
            from systems.glass import held_in
            _, outside, _ = held_in(cells, place.interior)
            cells, bed = cells[~outside], bed[~outside]
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
            sed.born = np.concatenate([sed.born, np.full(len(where), np.nan)])
        if len(sed.kg) > MOST_PARCELS:
            keep = slice(len(sed.kg) - MOST_PARCELS, None)
            sed.at, sed.grain, sed.kg, sed.born = sed.at[keep], sed.grain[keep], sed.kg[keep], sed.born[keep]
            if not self.warned:
                self.warned = True
                self.say("sediment_capped", parcels=MOST_PARCELS,
                         why="more sand in the water than is followed; the oldest is let go")

    def dredge(self, sed, place, water, dt, now=0.0) -> None:
        """What every dredger in the water loses this step, as parcels at its
        overflow: sand and silt by its share, spread over its hull's width."""
        world = getattr(place, "things", None)
        if world is None:
            return
        for one in world.of_kind("dredger"):
            said = one.said
            rate = float(said.get("releaseKgPerS", DREDGE_KG_PER_S))
            fines = float(said.get("finesShare", DREDGE_FINES))
            depth = float(said.get("releaseDepthM", 6.0))
            if rate <= 0.0:
                continue
            n = DREDGE_PARCELS_A_STEP
            at = np.repeat(np.array([[float(one.at[0]), float(one.at[1]), water.level - depth]]), n, axis=0)
            at[:, :2] += self.rng.normal(0.0, 0.5 * float(one.radius), (n, 2))
            bed = place.bottoms(at)
            at[:, 2] = np.maximum(at[:, 2], bed + 0.2)
            grain = (self.rng.random(n) < fines).astype(int)       # 1 is the silt
            kg = np.full(n, rate * dt / n)
            sed.at = np.vstack([sed.at, at])
            sed.grain = np.concatenate([sed.grain, grain])
            sed.kg = np.concatenate([sed.kg, kg])
            sed.born = np.concatenate([sed.born, np.full(n, float(now))])
            sed.lifted_kg += rate * dt
            sed.dredged_kg = getattr(sed, "dredged_kg", 0.0) + rate * dt
        if len(sed.kg) > MOST_PARCELS:
            keep = slice(len(sed.kg) - MOST_PARCELS, None)
            sed.at, sed.grain, sed.kg, sed.born = sed.at[keep], sed.grain[keep], sed.kg[keep], sed.born[keep]

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
        # And the sea's own mixing, in open water: without it a dredger's plume
        # an hour old was a metre wide. Horizontally Okubo's (1971) diffusion
        # diagram at a hundred metres' scale, vertically a coastal value; both
        # assumed for a place that has not measured its own. A tank's water is
        # mixed by its grid and its jets, as before.
        if place.interior is None and len(sed.at):
            sed.at[:, :2] += self.rng.normal(0.0, math.sqrt(2.0 * AMBIENT_KH * dt), (len(sed.at), 2))
            # Damped towards the bed, where the eddies are smaller than the
            # height they would carry a grain: nothing at the bed, all of it
            # a metre up. Undamped, it walked the silt a vehicle had just
            # lifted straight back into the sand.
            up = np.clip(sed.at[:, 2] - place.bottoms(sed.at), 0.0, 1.0)
            sed.at[:, 2] += self.rng.normal(0.0, 1.0, len(sed.at)) * np.sqrt(2.0 * AMBIENT_KV * up * dt)
        if place.interior is not None:
            from systems.glass import held_in
            sed.at[:, :2] = held_in(sed.at, place.interior)[0]
        sed.at[:, 2] = np.minimum(sed.at[:, 2], water.level - 0.005)
        bed = place.bottoms(sed.at)
        down = sed.at[:, 2] <= bed
        if down.any():
            sed.settled_kg += float(sed.kg[down].sum())
            self.on_the_coral(sed, coral, sed.at[down], sed.kg[down],
                              spread=_puff_m(now - sed.born[down]))
            keep = ~down
            sed.at, sed.grain, sed.kg, sed.born = sed.at[keep], sed.grain[keep], sed.kg[keep], sed.born[keep]

    @staticmethod
    def on_the_coral(sed, coral, where, kg, spread=None) -> None:
        """What lands within a colony's reach settles on it; a puff (a
        dredged parcel) settles as a Gaussian over its own width."""
        if coral is None or not len(coral):
            return
        if sed.on_coral_mg_cm2 is None or len(sed.on_coral_mg_cm2) != len(coral):
            sed.on_coral_mg_cm2 = np.zeros(len(coral))
        if not len(where):
            return
        if spread is not None:
            puff = np.isfinite(spread)
            for k in np.flatnonzero(puff):
                sigma = float(spread[k])
                near = coral.near(where[k], 3.0 * sigma)
                if not len(near):
                    continue
                d2 = ((coral.at[near, :2] - where[k, :2]) ** 2).sum(axis=1)
                # kg per m², as mg per cm²: ×1e6 mg/kg, ÷1e4 cm²/m².
                sed.on_coral_mg_cm2[near] += (float(kg[k]) / (2.0 * math.pi * sigma ** 2)
                                              * np.exp(-d2 / (2.0 * sigma ** 2)) * 100.0)
            where, kg = where[~puff], kg[~puff]
            if not len(where):
                return
        near = coral.near(where, 0.0)
        if not len(near):
            return
        radius = coral.radius[near]
        d = np.linalg.norm(where[:, None, :2] - coral.at[None, near, :2], axis=2)
        landed = d < radius[None, :]
        area_cm2 = math.pi * (radius * 100.0) ** 2
        sed.on_coral_mg_cm2[near] += (landed * kg[:, None]).sum(axis=0) * 1e6 / area_cm2

    def see(self, sed, v, now: float = 0.0) -> None:
        """How far the camera sees: the attenuation in the water just ahead of
        it, the water's own plus what is hanging there."""
        ahead = v.position + v.rotation @ np.array([0.25, 0.0, 0.0])
        # g/m³ of each grain, times what a gram in a cubic metre takes out.
        grams = hanging(sed, ahead, now, 0.25) * 1000.0
        added = sum(g * grain.attenuation for g, grain in zip(grams, GRAINS))
        sed.visibility_m = 4.8 / (self.CLEAR + added)
        sed.worst_visibility_m = (sed.visibility_m if sed.worst_visibility_m is None
                                  else min(sed.worst_visibility_m, sed.visibility_m))
