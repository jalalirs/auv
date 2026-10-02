"""The vehicle's own wash: a jet of water behind every thruster that is pushing.

Reads    thrust (what each thruster got), the vehicle (where they are), the water
Writes   wash: one jet a thruster, which anything in the water can ask about

A thruster pushes the vehicle one way by pushing water the other. That water
leaves the propeller as a jet, slows as it mixes with the water round it, and
spreads — and it is what lifts the sand under a vehicle hovering low, bends a
sea fan in front of one, and pushes a fish that strays behind one. The
vehicle's thrust is already in its own forces; this is the other half, put in
the water where the rest of the ocean can feel it.

The jet is the propeller-wash model harbour engineers use for scour, which is
analytic and runs in microseconds (Hamill, Kee & Ryan 2015; Stoschek 2014;
Albertson et al. 1950):

    efflux      V0 = sqrt(2 T / (rho A))      actuator disk, A the propeller's disc
    contracted  D0 = 0.71 Dp                  the jet just behind the propeller
    centreline  Vc = V0                        for x <= x0 = 2.8 D0 (the core)
                Vc = V0 x0 / x                 beyond it (Verhey's 2.78 D0/x)
    across      V = Vc exp(-22.2 (r / x)^2)    Albertson's Gaussian, x at least x0

A T200 at full power leaves at about 4.5 m/s and is about 0.7 m/s a metre on;
arXiv 2607.07139 fitted this kind of model to PIV behind an eight-thruster ROV
with R² 0.99 on the centreline. What it leaves out, and says so:

  - The jet is steady: it is where the thrusters point *now*. A real jet takes
    a moment to reach a metre away, and a turning vehicle sweeps a curved one.
  - It is not bent by the current, nor by the bed (Stoschek's near-bed
    correction is for later), nor does it draw water in from the sides.
  - Thrust here is the thrusters' rated thrust times the command, as it is in
    the vehicle's own forces.

These are the first things to replace if the wash is ever measured in the
tank, and the reason the wash is a part of its own: a grid fluid on the GPU
can stand in for this without anything that reads it changing.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

# Albertson's spread, and the jet's contraction and core.
SPREAD = 22.2
CONTRACTED = 0.71
CORE = 2.8
# How far a jet is followed, in propeller diameters. At sixty diameters a
# T200's jet is under a tenth of its efflux, and three metres behind it.
REACH = 60.0


class Wash:
    """Every thruster's jet, as it is this tick."""

    def __init__(self) -> None:
        self.origin = np.zeros((0, 3))     # where each jet leaves its propeller, world
        self.axis = np.zeros((0, 3))       # which way the water goes, unit, world
        self.efflux = np.zeros(0)          # V0, metres a second
        self.diameter = 0.0                # the propellers', metres
        self.from_ = "nothing yet"
        # The water the vehicle has already stirred, where a grid carries it
        # on (systems/flow.py); None in open water.
        self.grid = None

    def at(self, points) -> np.ndarray:
        """What the vehicle has done to the water at each of `points`: the jet
        where a thruster is pushing now, or the grid's lingering water where
        that is stronger — the wake it left, and the swirl off the glass."""
        jets = self.jets_at(points)
        if self.grid is None or not self.grid.on:
            return jets
        stirred = self.grid.at(points)
        stronger = np.linalg.norm(stirred, axis=1) > np.linalg.norm(jets, axis=1)
        return np.where(stronger[:, None], stirred, jets)

    def jets_at(self, points) -> np.ndarray:
        """The jets' velocity at each of `points` (n, 3), metres a second."""
        points = np.atleast_2d(np.asarray(points, dtype=float))
        out = np.zeros_like(points)
        live = self.efflux > 1e-6
        if not live.any() or self.diameter <= 0:
            return out
        dp = self.diameter
        x0 = CORE * CONTRACTED * dp
        for origin, axis, v0 in zip(self.origin[live], self.axis[live], self.efflux[live]):
            off = points - origin
            x = off @ axis
            ahead = (x > 0.0) & (x < REACH * dp)
            if not ahead.any():
                continue
            xs = x[ahead]
            r = np.linalg.norm(off[ahead] - xs[:, None] * axis[None, :], axis=1)
            centre = v0 * np.minimum(1.0, x0 / xs)
            spread = np.maximum(xs, x0)
            out[ahead] += (centre * np.exp(-SPREAD * (r / spread) ** 2))[:, None] * axis[None, :]
        return out


class WashSystem(System):
    name = "wash"
    reads = ("thrust", "vehicle", "water")
    writes = ("wash",)

    def __init__(self, thrusters) -> None:
        # Where each thruster is on the hull and which way it pushes it, in
        # the body frame, and how hard it can.
        self.at_on_hull = np.array([t.position for t in thrusters], dtype=float).reshape(-1, 3)
        self.pushes = np.array([t.direction for t in thrusters], dtype=float).reshape(-1, 3)
        norms = np.linalg.norm(self.pushes, axis=1, keepdims=True)
        self.pushes = self.pushes / np.maximum(norms, 1e-12)
        self.forward_n = np.array([t.max_forward_n for t in thrusters], dtype=float)
        self.reverse_n = np.array([t.max_reverse_n for t in thrusters], dtype=float)

    def step(self, world) -> None:
        wash, thrust, v = world.wash, world.thrust, world.vehicle
        if thrust.diameter_m is None or not len(self.at_on_hull):
            return
        c = np.clip(np.asarray(thrust.commands, dtype=float), -1.0, 1.0)
        newtons = np.abs(c) * np.where(c >= 0.0, self.forward_n, self.reverse_n)
        # Under the surface only: a thruster in air moves air.
        submerged = v.submerged(world.water.level)
        rho = float(world.water.density_at(max(0.0, float(-v.position[2]))))
        disc = math.pi * (0.5 * thrust.diameter_m) ** 2
        wash.diameter = float(thrust.diameter_m)
        wash.efflux = np.sqrt(2.0 * newtons / (rho * disc)) * submerged
        wash.origin = v.position[None, :] + self.at_on_hull @ v.rotation.T
        # The water goes the other way from the push it gives.
        wash.axis = -(np.sign(c)[:, None] * (self.pushes @ v.rotation.T))
        wash.from_ = ("derived: a propeller-wash jet (Hamill; Verhey; Albertson) from each "
                      "thruster's rated thrust times its command, and the propeller diameter "
                      "the vehicle package states")
