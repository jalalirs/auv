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


class Place:
    def __init__(self) -> None:
        self.seabed = None
        self.floor = None
        self.interior = None
        self.things = None

    def bottom_under(self, position) -> float | None:
        """Where the bottom is under a point: the heightfield's, or the flat
        floor's, or nowhere."""
        if self.seabed is not None:
            return self.seabed.under(float(position[0]), float(position[1]))
        return self.floor
