"""What is in the water besides the vehicle.

A place is a seabed and its coral, and both are read from a survey. That is the
right foundation and it is not a site. What a dive actually happens in is a
site somebody *arranged*: an array laid in a particular pattern, a ship holding
station over there, a nursery frame here, a line running between those two
points. None of it is in the survey, all of it is in the water, and a vehicle
flown through it has to be able to run into it.

This is where those live. It is a module rather than eleven more methods on the
dive because everything about the world that is still to come — lines that bow
with the current, a tether that pulls back, things that move — lands here, and
a class with fifty-nine methods does not want twelve more.

Two things it does, and they are separate on purpose:

  **Truth.** Where each thing is, in the world's own coordinates, resolved when
  it was drawn rather than when it is flown. A task scores against this, and a
  sonar will eventually see it.

  **Obstruction.** A vehicle driven at a mooring block stops, the same way it
  stops against the ground — two constraints resolved by putting the vehicle
  back where it was allowed to be and taking away the velocity that carried it
  out. Not a collision solver: a hard stop does not bounce and does not keep
  pushing.
"""

from __future__ import annotations

import math

import numpy as np

# How big each kind of thing is, in metres, as a radius and a height. Coarse on
# purpose: what matters to a vehicle at half a metre a second is whether
# something is there, not the shape of its corners.
SIZES = {
    "transponder":     (0.35, 2.0),
    "mooring-block":   (0.8, 0.6),
    "nursery-frame":   (2.0, 1.2),
    "marker-post":     (0.2, 3.0),
    "buoy":            (0.5, 0.8),
    "ship":            (6.0, 3.0),
}
DEFAULT_SIZE = (0.6, 1.0)


class Thing:
    """One thing somebody put in the water."""

    __slots__ = ("id", "kind", "at", "radius", "height", "said")

    def __init__(self, said: dict) -> None:
        self.said = dict(said)
        self.id = str(said.get("id") or "")
        self.kind = str(said.get("kind") or "thing")
        # Where it is. `z` is what the landing rule resolved to when it was
        # drawn — against that seabed, which is why a layout belongs to a place
        # and is wrong anywhere else.
        z = said.get("z")
        if z is None:
            ground = said.get("groundM")
            z = -float(ground) if ground is not None else 0.0
        self.at = np.array([float(said.get("x", 0.0)), float(said.get("y", 0.0)),
                            float(z)], dtype=float)
        radius, height = SIZES.get(self.kind, DEFAULT_SIZE)
        self.radius = float(said.get("radiusM", radius))
        self.height = float(said.get("heightM", height))

    def near(self, position, margin: float = 0.0) -> bool:
        """Whether a point is inside this thing, plus a margin."""
        flat = float(np.hypot(position[0] - self.at[0], position[1] - self.at[1]))
        if flat > self.radius + margin:
            return False
        low, high = self.at[2], self.at[2] + self.height
        return (low - margin) <= float(position[2]) <= (high + margin)

    def described(self) -> dict:
        return {"id": self.id, "kind": self.kind,
                "at": [round(float(v), 2) for v in self.at],
                "radiusM": round(self.radius, 2), "heightM": round(self.height, 2)}


class World:
    """Everything a place was arranged with, and what it does to a vehicle."""

    def __init__(self, document: dict | None = None) -> None:
        self.things: list[Thing] = []
        self.version = ""
        self.struck = 0
        if isinstance(document, dict):
            for said in document.get("things") or []:
                if isinstance(said, dict):
                    self.things.append(Thing(said))

    def __len__(self) -> int:
        return len(self.things)

    def of_kind(self, kind: str) -> list[Thing]:
        return [one for one in self.things if one.kind == kind]

    def by_id(self, which: str) -> Thing | None:
        return next((one for one in self.things if one.id == which), None)

    def keep_out(self, position, was, half_width: float):
        """Stop a vehicle that has been driven into something.

        The same two constraints the ground applies: put it back where it was
        allowed to be, and take away the velocity that carried it out. A thing
        in the water is not a wall to slide along and not a spring to bounce
        off; it is somewhere the vehicle cannot be.

        Answers the position it is allowed to hold and what it struck, or the
        position unchanged and nothing.
        """
        for thing in self.things:
            if not thing.near(position, half_width):
                continue
            # Out the way it came in. Pushing it to the nearest face would
            # slide a vehicle round an obstacle it drove straight at, which is
            # a vehicle passing through something slowly.
            away = np.array([position[0] - thing.at[0], position[1] - thing.at[1], 0.0])
            flat = float(np.hypot(away[0], away[1]))
            if flat < 1e-6:
                away = np.array([float(was[0] - thing.at[0]),
                                 float(was[1] - thing.at[1]), 0.0])
                flat = float(np.hypot(away[0], away[1])) or 1.0
            out = position.copy()
            reach = thing.radius + half_width
            out[0] = thing.at[0] + away[0] / flat * reach
            out[1] = thing.at[1] + away[1] / flat * reach
            self.struck += 1
            return out, thing
        return position, None

    def described(self) -> dict:
        """What is in the water, for the record and for a console."""
        counted: dict[str, int] = {}
        for one in self.things:
            counted[one.kind] = counted.get(one.kind, 0) + 1
        return {"things": len(self.things), "of": counted,
                "struck": self.struck,
                "layoutVersion": self.version or None}
