"""The water's push on a hull, panel by panel.

The coefficient model gives each axis a drag that goes as its speed squared,
and treats the axes as if they did not touch: a vehicle turning while it moves
ahead is damped as if it did one and then the other, and a rotation's drag is
a number nobody could take from the hull (estimated from a silhouette it came
out five to twenty times under what was measured).

This takes it from the hull instead. Every panel of the hull meets the water
at its own velocity — the vehicle's, plus its turning times its arm, less the
water's own motion where the panel is — and pushes back:

  a face meeting the water   the stagnation pressure, ½ρ C_front (v·n)², inward
  a face leaving it          the base suction behind it, ½ρ C_back (v·n)², drawn
                             back the way it came — where it opens on the wake

summed into a force and its moment about the centre. So a turn is damped by
what the hull's ends sweep through, a translation by what its faces meet, and
both at once by the same panels, with no axis knowing about any other.

What an open frame hides from the water is the other half of it. A panel the
oncoming water cannot reach straight — it is behind another part of the hull,
seen from that direction — sits in that part's wake and meets the water slowed
down. How shielded each panel is, from each of a set of directions, is worked
out once from the mesh (hardware/hull_panels.py); here the nearest direction
to the water's is looked up. How much slower the water is in a wake is the one
number in this fitted to a measurement, and the package says which.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np


class Panels:
    """A hull's panels and how the water reaches them."""

    def __init__(self, document: dict) -> None:
        self.at = np.asarray(document["centresM"], dtype=float)          # (n, 3), body frame
        self.normal = np.asarray(document["normals"], dtype=float)        # (n, 3), outward
        self.area = np.asarray(document["areasM2"], dtype=float)          # (n,)
        self.directions = np.asarray(document["directions"], dtype=float)  # (k, 3), unit
        # (k, n): 1 where the panel meets the oncoming water straight, 0 where
        # it is behind something, seen from that direction.
        self.open = np.asarray(document["exposed"], dtype=float)
        self.front = float(document.get("frontCoefficient", 0.8))
        self.back = float(document.get("backCoefficient", 0.37))
        self.wake = float(document.get("wakeShare", 0.5))
        self.rotation_quadratic = np.asarray(document.get("rotationQuadratic", [0.0, 0.0, 0.0]), dtype=float)
        self.from_ = str(document.get("from", ""))

    @classmethod
    def of(cls, package: pathlib.Path) -> "Panels | None":
        """A vehicle package's panels, when it has them."""
        path = pathlib.Path(package) / "panels.json"
        if not path.exists():
            return None
        return cls(json.loads(path.read_text()))

    def wrench(self, velocity: np.ndarray, rho: float, water_at=None) -> np.ndarray:
        """The water's push on the hull, a body-frame wrench.

        `velocity` is the body twist through the water at the centre (linear,
        then angular). `water_at`, when given, is the water's own velocity at
        each panel in the body frame beyond what the twist already took off —
        the wash, the eddies a grid carries — so a panel in a jet feels it.
        """
        v = np.asarray(velocity[:3], dtype=float)
        w = np.asarray(velocity[3:6], dtype=float)
        # Each panel's velocity through the water.
        moving = v[None, :] + np.cross(w[None, :], self.at)
        if water_at is not None:
            moving = moving - np.asarray(water_at, dtype=float)
        into = np.einsum("ij,ij->i", moving, self.normal)       # >0: meeting the water
        speed = float(np.linalg.norm(v))
        if speed > 1e-6:
            ahead = self.directions @ (v / speed)
            reach = self.open[int(np.argmax(ahead))]
            # A face leaving the water is drawn back only where the water it
            # leaves is the wake's: open downstream. One shut inside the hull
            # (a battery tube behind the shell) has no wake behind it to pull.
            behind = self.open[int(np.argmin(ahead))]
        else:
            reach = behind = np.ones(len(self.area))
        # The water a shielded panel meets is slowed in the wake in front of it.
        slowed = reach + (1.0 - reach) * self.wake
        pressure = np.where(into > 0.0,
                            -self.front * slowed * slowed * into * into,   # pushed in
                            self.back * behind * into * into)               # drawn back
        force = (0.5 * rho * pressure * self.area)[:, None] * self.normal
        return np.concatenate([force.sum(axis=0), np.cross(self.at, force).sum(axis=0)])
