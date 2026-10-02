"""A ship towing something: the ship, where its cable leaves it, and the fish on the end.

Reads    the clock
Writes   ship: where the ship is and how fast it goes

A towed sensor — a side-scan towfish like KAUST's EdgeTech 2300 — has no
thrusters. It is flown by the ship: how fast she goes and how much cable is
out decide how deep the fish flies, and the fish's own weight and drag decide
how it hangs. So the ship is the controller. She steams a straight line at the
tow speed the dive asks for, and the cable's dry end is her stern
(systems/tether.py reads it there). Everything else — the catenary of a
hundred metres of armoured cable, the fish swinging in behind as she turns —
is the cable and the fish's own physics.

The dive asks for a tow in its objective:

    "tow": {"speedKn": 4, "headingDeg": 90, "cableOutM": 60}

Assumed: the ship is not moved by the sea or by her cable — a few kilonewtons
on a survey vessel's stern is nothing to her.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

KNOT = 0.514444


class Ship:
    def __init__(self) -> None:
        self.towing = False
        self.at = np.zeros(3)             # the stern, where the cable leaves her; z at the waterline
        self.velocity = np.zeros(3)
        self.speed_kn = 0.0
        self.heading_deg = 0.0
        self.cable_out_m = 0.0

    def set_for(self, tow: dict, starts_at) -> None:
        self.towing = True
        self.speed_kn = float(tow.get("speedKn", 4.0))
        self.heading_deg = float(tow.get("headingDeg", 0.0))
        self.cable_out_m = float(tow.get("cableOutM", 50.0))
        a = math.radians(self.heading_deg)
        speed = self.speed_kn * KNOT
        self.velocity = np.array([speed * math.cos(a), speed * math.sin(a), 0.0])
        self.at = np.array([float(starts_at[0]), float(starts_at[1]), 0.0])

    def said(self) -> dict:
        return {"speedKn": self.speed_kn, "headingDeg": self.heading_deg, "cableOutM": self.cable_out_m,
                "at": [round(float(c), 1) for c in self.at]}


class ShipSystem(System):
    name = "ship"
    before = ("clock",)
    writes = ("ship",)

    def __init__(self, dt: float) -> None:
        self.dt = float(dt)

    def step(self, world) -> None:
        ship = world.ship
        if ship.towing:
            ship.at = ship.at + ship.velocity * self.dt
