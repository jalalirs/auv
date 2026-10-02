"""The ground, the glass, what is in the water, and the cable: stopping the hull.

Not a collision solver, yet. Each is a constraint resolved the same way: put
the vehicle back where it was allowed to be, and take away the part of its
motion that was carrying it out. That is what a hard stop does — it does not
bounce and it does not keep pushing — and a vehicle held against a wall still
slides along it, which is what a pilot expects. Every contact is counted once
per contact, not once per step: a vehicle held against a frame for four
seconds struck it once.

These are functions the vehicle system calls after it moves, on the state it
owns. When contact becomes a system of its own with forces and impulses (r6
item 4), these are what it replaces, and `Contacts` is the part it will own.
"""

from __future__ import annotations

import math

import numpy as np


class Contacts:
    """What the dive has touched so far."""

    def __init__(self) -> None:
        self.struck: set[str] = set()        # things in the water, by id
        self.grounded = 0                    # times it was stopped by ground it could not ride over
        self.glass = 0                       # times it touched a tank's glass
        self.on_the_glass = False

    def said(self) -> dict:
        return {"things": len(self.struck), "which": sorted(self.struck),
                "ground": int(self.grounded), "glass": int(self.glass)}


# Ground steeper than this is a wall rather than a slope: a vehicle rides over
# what it can and is stopped by what it cannot. Fifty degrees is well past
# anything a reef's sand or rubble holds, and short of the near vertical faces
# of a spur, which is exactly the line worth drawing.
CLIMBS_UP_TO = math.cos(math.radians(50.0))


def land(v, place, contacts, cable, dt: float, say) -> None:
    """Stop the vehicle where the ground is: under it, and ahead of it; and
    at the glass, at anything in the water, and at the end of its cable."""
    floor = place.bottom_under(v.position)
    if floor is not None:
        bottom = floor + v.half_height
        if v.position[2] < bottom:
            v.position[2] = bottom
            settle(v, place)
        else:
            v.on_the_bottom = False
    strike(v, place, contacts)
    keep_out_of_things(v, place, contacts, dt, say)
    keep_inside_the_glass(v, place, contacts, say)
    stay_on_the_cable(v, cable, dt, say)
    # There is no lid on the surface. A vehicle that breaks it loses its
    # buoyancy and its thrust as it emerges and falls back on its own, which is
    # what a real one does and is worth being able to see happen.


def settle(v, place) -> None:
    """Take away the motion going into the ground, and leave the rest.

    The ground is a surface, not a lift: on a flat bottom the descent stops,
    on a slope the push turns into travel along it and the vehicle keeps only
    what it did not spend climbing, and on a face near vertical almost nothing
    of it is left.
    """
    facing = (np.array([0.0, 0.0, 1.0]) if place.seabed is None
              else place.seabed.normal(float(v.position[0]), float(v.position[1])))
    moving = v.rotation @ v.velocity[:3]
    into = float(np.dot(moving, facing))
    if into < 0.0:
        v.velocity[:3] = v.rotation.T @ (moving - facing * into)
    # Ground it is resting on, or a face it is up against. One is a dive that
    # has landed, the other a dive that is stuck.
    v.on_the_bottom = bool(facing[2] > 0.7)
    if facing[2] <= 0.7:
        v.against_the_ground = True


def strike(v, place, contacts) -> None:
    """Stop the vehicle against ground it cannot ride over.

    It looks along the way it is actually moving, ahead and out to its sides —
    a hull is as wide as its arms, not as wide as a point — and if the ground
    there stands above its keel and faces too steeply to be a slope, the part
    of its motion going into that face is taken away.
    """
    if place.seabed is None:
        return
    moving = v.rotation @ v.velocity[:3]
    flat = moving[:2]
    speed = float(np.linalg.norm(flat))
    if speed < 1e-4:
        return
    way = flat / speed
    side = np.array([-way[1], way[0]])
    keel = float(v.position[2]) - v.half_height
    touched = False
    for along, across in ((1.0, 0.0), (0.7, 0.6), (0.7, -0.6), (0.0, 0.75), (0.0, -0.75)):
        probe = v.position[:2] + (way * along + side * across) * v.half_width
        there = place.seabed.under(float(probe[0]), float(probe[1]))
        if there <= keel:
            continue
        facing = place.seabed.normal(float(probe[0]), float(probe[1]))
        if facing[2] >= CLIMBS_UP_TO:
            continue                    # a slope, not a wall: it may ride up
        into = facing[:2]
        length = float(np.linalg.norm(into))
        if length < 1e-9:
            continue
        into = into / length
        going = float(np.dot(flat, into))
        if going >= 0.0:
            continue                    # already leaving the face
        flat = flat - into * going
        touched = True
    if not touched:
        return
    moving[:2] = flat
    v.velocity[:3] = v.rotation.T @ moving
    if not v.against_the_ground:
        contacts.grounded += 1
    v.against_the_ground = True


def keep_out_of_things(v, place, contacts, dt: float, say) -> None:
    """Stop the vehicle against what somebody put in the water: somewhere it
    cannot be, not a wall to slide along and not a spring to bounce off."""
    things = place.things
    if things is None or not len(things):
        return
    going = v.rotation @ v.velocity[:3]
    came_from = v.position - going * max(1e-3, dt)
    allowed, struck = things.keep_out(v.position, came_from, v.half_width)
    if struck is None:
        return
    moved = allowed - v.position
    v.position = allowed
    # Only the part of the motion that was going into it.
    flat = np.array([moved[0], moved[1], 0.0])
    reach = float(np.linalg.norm(flat))
    if reach > 1e-9:
        out = flat / reach
        through = v.rotation @ v.velocity[:3]
        into = float(np.dot(through, out))
        if into < 0.0:
            v.velocity[:3] = v.rotation.T @ (through - out * into)
    if struck.id not in contacts.struck:
        contacts.struck.add(struck.id)
        say("struck", what=struck.kind, which=struck.id, is_=struck.spec.what,
            where=[round(float(c), 2) for c in allowed])


def keep_inside_the_glass(v, place, contacts, say) -> None:
    """Stop at a tank's walls the way the ground stops it. A vehicle against
    the glass has hit the tank, and is counted: leaving it out made a
    controller that scraped the glass all the way round look as clean as one
    that never touched it."""
    if place.interior is None:
        return
    low, high = place.interior
    reach = float(v.half_width)
    touching = False
    for axis in (0, 1):
        lo, hi = float(low[axis]) + reach, float(high[axis]) - reach
        if v.position[axis] < lo or v.position[axis] > hi:
            v.position[axis] = min(max(float(v.position[axis]), lo), hi)
            normal = np.zeros(3)
            normal[axis] = 1.0
            into = v.rotation.T @ normal
            along = float(np.dot(v.velocity[:3], into))
            v.velocity[:3] -= along * into
            if not contacts.on_the_glass:
                contacts.glass += 1
                say("touched_the_glass", axis="xy"[axis], times=contacts.glass,
                    at=[round(float(c), 3) for c in v.position])
            touching = True
    contacts.on_the_glass = touching


def stay_on_the_cable(v, cable, dt: float, say) -> None:
    """A vehicle cannot go further out than there is cable: put back where the
    tether allows, and the motion carrying it further out taken away."""
    if cable is None or not cable.out:
        return
    came_from = v.position - (v.rotation @ v.velocity[:3]) * max(1e-3, dt)
    allowed, held = cable.keep_in(v.position, came_from)
    if not held:
        return
    v.position = allowed
    out = allowed - cable.at
    far = float(np.linalg.norm(out))
    if far < 1e-9:
        return
    out = out / far
    through = v.rotation @ v.velocity[:3]
    away = float(np.dot(through, out))
    if away > 0.0:
        v.velocity[:3] = v.rotation.T @ (through - out * away)
    if cable.struck == 1:
        say("tether_taut", lengthM=round(cable.length_m, 1),
            from_=[round(float(c), 1) for c in cable.at],
            why="a vehicle cannot go further out than there is cable")
