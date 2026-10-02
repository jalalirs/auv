"""The ground, the glass, what is in the water, and the cable: stopping the hull.

Each is a constraint resolved the same way: put the vehicle back where it was
allowed to be, and turn round the part of its motion that was carrying it in —
most of it lost, a quarter of it kept (RESTITUTION), because a hull that hits
rock under water comes back off it a little and not at all like a ball. The
rest of its motion is left alone, so a vehicle pressed against a wall still
slides along it, which is what a pilot expects. Settling onto the bottom is
the exception: a vehicle landing does not bounce. Every contact is counted once
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
        self.clear_for_s = 1e9               # how long since it was last against a face
        self.cable_held = 0                  # times it reached the end of its cable
        self.at_full_scope = False
        # Every strike, with where, how fast into the surface, and the impulse
        # it took to stop that: what a strike *was*, not only that there was
        # one. And the coral struck, by colony, for the coral to judge.
        self.strikes: list[dict] = []
        self.coral_hits: list[dict] = []
        self.on_coral: set[int] = set()

    def strike_of(self, what: str, where, into_ms: float, v) -> dict:
        """Record a strike: its speed into the surface and the impulse to stop
        it, from the vehicle's effective mass across the flow."""
        mass = float(np.mean(v.effective[:2]))
        hit = {"what": what, "at": [round(float(c), 3) for c in where],
               "speedMs": round(float(into_ms), 4), "impulseNs": round(mass * float(into_ms), 4)}
        self.strikes.append(hit)
        return hit

    def said(self) -> dict:
        return {"things": len(self.struck), "which": sorted(self.struck),
                "ground": int(self.grounded), "glass": int(self.glass),
                "coral": len({h["colony"] for h in self.coral_hits})}

    def hardest(self) -> dict | None:
        """The hardest strike of the dive."""
        return max(self.strikes, key=lambda s: s["impulseNs"]) if self.strikes else None


# How much of its speed into a hard surface a hull keeps, coming back off it.
# Underwater, little: the water round the hull goes on moving and most of the
# energy of a knock goes into it and into the hull's own give. A quarter,
# assumed — the figure a drop test in the tank would settle.
RESTITUTION = 0.25

# Ground steeper than this is a wall rather than a slope: a vehicle rides over
# what it can and is stopped by what it cannot. Fifty degrees is well past
# anything a reef's sand or rubble holds, and short of the near vertical faces
# of a spur, which is exactly the line worth drawing.
CLIMBS_UP_TO = math.cos(math.radians(50.0))


def land(v, place, contacts, cable, dt: float, say, coral=None) -> None:
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
    keep_out_of_coral(v, coral, contacts, say)
    keep_inside_the_glass(v, place, contacts, say)
    stay_on_the_cable(v, cable, contacts, dt, say)
    contacts.clear_for_s = 0.0 if v.against_the_ground else contacts.clear_for_s + dt
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
        flat = flat - into * going * (1.0 + RESTITUTION)
        touched = True
    if not touched:
        return
    taken = float(np.linalg.norm(moving[:2] - flat))
    moving[:2] = flat
    v.velocity[:3] = v.rotation.T @ moving
    # Once a contact: a vehicle scraping along a face for a second struck it
    # once, not two hundred times — and a scrape that touches and lets go
    # every other step as it slides is one scrape, so a new strike needs half
    # a second clear of the last.
    if not v.against_the_ground and contacts.clear_for_s > 0.5:
        contacts.grounded += 1
        contacts.strike_of("ground", v.position, taken, v)
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
            v.velocity[:3] = v.rotation.T @ (through - out * into * (1.0 + RESTITUTION))
    else:
        into = 0.0
    if struck.id not in contacts.struck:
        contacts.struck.add(struck.id)
        contacts.strike_of(str(struck.id), allowed, -min(0.0, into) if reach > 1e-9 else 0.0, v)
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
            v.velocity[:3] -= along * into * (1.0 + RESTITUTION)
            if not contacts.on_the_glass:
                contacts.glass += 1
                contacts.strike_of("glass", v.position, abs(along), v)
                say("touched_the_glass", axis="xy"[axis], times=contacts.glass,
                    at=[round(float(c), 3) for c in v.position])
            touching = True
    contacts.on_the_glass = touching


def keep_out_of_coral(v, coral, contacts, say) -> None:
    """Stop the vehicle at a colony as at rock, and tell the coral it was hit.

    A colony is a column of its own width and its height now (a broken one is
    a stump). One that bends — a soft coral, a fan, a sponge — does not stop
    the vehicle; it is brushed, and counted."""
    if coral is None or not len(coral):
        return
    off = v.position[:2][None, :] - coral.at[:, :2]
    far = np.linalg.norm(off, axis=1)
    # The hull's outline from above: an ellipse its length by its beam, turned
    # with it — a vehicle passing a colony side-on reaches half its beam, not
    # half its length. A colony meets it where the ellipse, grown by the
    # colony's radius, holds the colony's middle.
    length, beam = v.footprint or (float(v.half_width), float(v.half_width))
    heading = math.atan2(float(v.rotation[1, 0]), float(v.rotation[0, 0]))
    c, s = math.cos(heading), math.sin(heading)
    ahead = -(off[:, 0] * c + off[:, 1] * s)
    aside = -(-off[:, 0] * s + off[:, 1] * c)
    inside = (ahead / (length + coral.radius)) ** 2 + (aside / (beam + coral.radius)) ** 2 < 1.0
    # How far out it must be put, along the line between them: where that
    # line leaves the grown ellipse.
    angle = np.arctan2(aside, ahead)
    reach = 1.0 / np.sqrt((np.cos(angle) / (length + coral.radius)) ** 2
                          + (np.sin(angle) / (beam + coral.radius)) ** 2)
    level = (v.position[2] - v.half_height < coral.at[:, 2] + coral.height) & \
            (v.position[2] + v.half_height > coral.at[:, 2])
    touching = set(np.flatnonzero(inside & level).tolist())
    solid = coral.solid()
    for i in sorted(touching):
        out = off[i] / max(float(far[i]), 1e-9)
        into = 0.0
        if solid[i]:
            v.position[:2] = coral.at[i, :2] + out * reach[i]
            through = v.rotation @ v.velocity[:3]
            going = float(np.dot(through[:2], out))
            if going < 0.0:
                flat = np.array([out[0], out[1], 0.0])
                v.velocity[:3] = v.rotation.T @ (through - flat * going * (1.0 + RESTITUTION))
                into = -going
        if i not in contacts.on_coral:
            hit = contacts.strike_of(f"coral-{i}", v.position, into, v)
            contacts.coral_hits.append({"colony": i, **hit})
            if solid[i]:
                say("struck_coral", which=i, growth=str(coral.kind[i]), speedMs=hit["speedMs"],
                    impulseNs=hit["impulseNs"])
    contacts.on_coral = touching


def stay_on_the_cable(v, cable, contacts, dt: float, say) -> None:
    """A vehicle cannot go further out than there is cable: put back where the
    tether allows, and the motion carrying it further out taken away."""
    if cable is None or not cable.out:
        return
    came_from = v.position - (v.rotation @ v.velocity[:3]) * max(1e-3, dt)
    allowed, held = cable.keep_in(v.position, came_from)
    if not held:
        contacts.at_full_scope = False
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
    if not contacts.at_full_scope:
        contacts.cable_held += 1
        if contacts.cable_held == 1:
            say("tether_taut", lengthM=round(cable.length_m, 1),
                from_=[round(float(c), 1) for c in cable.at],
                why="a vehicle cannot go further out than there is cable")
    contacts.at_full_scope = True
