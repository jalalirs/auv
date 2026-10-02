"""The place: what the dive happens in, which nothing changes while it runs.

    seabed     the heightfield, asked where the bottom is and which way it faces
    floor      a flat bottom, for a place with no heightfield
    interior   a tank's inside, (low, high) corners: the glass
    things     what somebody put in the water: frames, blocks, a dock

Written when the place is opened and read by everything after. It has no
system, because nothing in a dive moves the seabed — yet. When coral breaks
(r6 item 6) the colonies become a part of their own, with an owner.
"""

from __future__ import annotations

import numpy as np


class Place:
    def __init__(self) -> None:
        self.seabed = None
        self.floor = None
        self.interior = None
        self.things = None

    def bottoms(self, points) -> np.ndarray:
        """Where the bottom is under each of many points; -inf where there is
        none."""
        points = np.atleast_2d(np.asarray(points, dtype=float))
        if self.seabed is not None:
            many = getattr(self.seabed, "under_many", None)
            if many is not None:
                return many(points[:, 0], points[:, 1])
            return np.array([self.seabed.under(float(x), float(y)) for x, y in points[:, :2]])
        return np.full(len(points), -np.inf if self.floor is None else float(self.floor))

    def facing(self, points) -> np.ndarray:
        """Which way the bottom faces under each of many points, (n, 3)."""
        points = np.atleast_2d(np.asarray(points, dtype=float))
        if self.seabed is None:
            return np.tile([0.0, 0.0, 1.0], (len(points), 1))
        many = getattr(self.seabed, "normal_many", None)
        if many is not None:
            return many(points[:, 0], points[:, 1])
        return np.array([self.seabed.normal(float(x), float(y)) for x, y in points[:, :2]])

    def bottom_under(self, position) -> float | None:
        """Where the bottom is under a point: the heightfield's, or the flat
        floor's, or nowhere."""
        if self.seabed is not None:
            return self.seabed.under(float(position[0]), float(position[1]))
        return self.floor
