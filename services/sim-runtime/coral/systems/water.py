"""The water's own motion, where anything is in it.

Reads    faults (a gust is a change in the current)
Writes   water: the current, the wind over the surface, the waves, the surface

Three things move the water a vehicle is in, and all of them are here:

  **The current**, from the dive's conditions, uniform in a place. In a tank it
  is the circulation pump.
  **The wind's drift**: the top of the water dragged along by the wind, about
  three per cent of it, dying away a few centimetres down. In a tank, a fan.
  **The waves' orbits**, from the sea state, dying as exp(-kz) with depth —
  which is why shallow work stops when the weather comes up and a dive at
  forty metres does not care.

What reads the water asks it for the motion at a point (`moving_at`) rather
than reaching for the current, so that when the vehicle's own thruster wash is
added to it (r6 item 3) everything that feels the water feels the wash
without being changed.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System


class Water:
    # The surface drift a wind drives is about three per cent of the wind, the
    # oceanographer's rule of thumb, and in a tank it is gone a few centimetres
    # down. Both are guesses with a shape, and the second is the one a fan and
    # a dye trace would settle.
    WIND_DRIFT = 0.03
    WIND_REACHES_M = 0.06

    def __init__(self) -> None:
        self.current = np.zeros(3)
        self.wind = np.zeros(3)
        self.sea = None              # the sea state and the surface (water.py), when the place has one
        self.level = 0.0             # where the surface is, metres
        # The column, as the conditions describe it: given when the dive is
        # built, because what the water is at a depth is the conditions'
        # business and not the water's motion.
        self.temperature_at = lambda depth: None
        self.density_at = lambda depth: 1025.0
        self.salinity = None

    def wind_drift(self, position, half_height: float):
        """The top of the water dragged along by the wind, at a hull whose
        top is half_height above `position`."""
        if not self.wind.any():
            return np.zeros(3)
        depth = max(0.0, float(-position[2]) - float(half_height))
        return self.WIND_DRIFT * self.wind * math.exp(-depth / self.WIND_REACHES_M)

    def orbital(self, position, half_height: float, t: float):
        """The water's own motion under the waves, and the wind's drift."""
        if self.sea is None or not hasattr(self.sea, "orbital_here"):
            return self.wind_drift(position, half_height)
        return self.wind_drift(position, half_height) + self.sea.orbital_here(
            float(position[0]), float(position[1]), max(0.0, float(-position[2])), t)

    def flow_at(self, points, t: float) -> np.ndarray:
        """The water's own motion at each of `points` (n, 3): the current, the
        wind's drift and the waves' orbits. Not the wash: that is the
        vehicle's, in systems/wash.py, and whoever wants both adds them."""
        points = np.atleast_2d(np.asarray(points, dtype=float))
        out = np.broadcast_to(self.current, points.shape).copy()
        if self.wind.any():
            depth = np.maximum(0.0, -points[:, 2])
            out += self.WIND_DRIFT * np.exp(-depth / self.WIND_REACHES_M)[:, None] * self.wind[None, :]
        many = getattr(self.sea, "orbital_many", None)
        if many is not None:
            out += many(points, t)
        return out


class WaterSystem(System):
    name = "water"
    reads = ("faults",)
    writes = ("water",)

    def __init__(self, say) -> None:
        self.say = say
        self.gusts_taken = 0

    def step(self, world) -> None:
        water, gusts = world.water, world.faults.gusts
        while self.gusts_taken < len(gusts):
            water.current = water.current + gusts[self.gusts_taken]
            self.gusts_taken += 1
            self.say("gust", currentMs=round(float(np.hypot(*water.current[:2])), 3))
