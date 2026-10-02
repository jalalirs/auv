"""The hull, moved by its thrusters, the water and its cable.

Reads    thrust, the water, the helm (its actuators), the place
Writes   vehicle (where it is and how it moves), contacts
Before   the clock: it moves the vehicle from the start of the tick to the end;
         and the cable, whose pull it feels as the cable left it last tick

The forces are hydrodynamics.py: thrust, drag on the motion *through the
water*, buoyancy and its righting moment, added mass, all for the share of the
hull that is under the surface. This takes the water's own motion off the
vehicle's before the hull sees it — so a vehicle doing nothing in a current is
carried by it — adds the cable's pull, integrates, and then stops it against
whatever it cannot pass (contact.py).

Semi-implicit Euler at a fixed step. Not because it is the best integrator but
because it is the same integrator every time, which matters more than accuracy
for a result two runs must agree on.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System
from systems import contact


class Vehicle:
    def __init__(self, body, position) -> None:
        self.body = body                          # hydrodynamics.Body: the hull and its thrusters
        self.position = np.asarray(position, dtype=float)
        self.velocity = np.zeros(6)               # body frame: surge, sway, heave, roll, pitch, yaw rates
        self.rotation = np.eye(3)                 # body to world
        self.effective = body.effective_mass() if body is not None else np.ones(6)
        self.half_width = 0.3
        self.half_height = 0.15
        self.on_the_bottom = False
        self.against_the_ground = False
        # How hard it was working, last step. What frightens the fish.
        self.wrench = None
        # Half its length and half its beam, when its hull says: its outline
        # from above, which is what meets a colony as it passes.
        self.footprint: tuple[float, float] | None = None

    def submerged(self, level) -> float:
        """The share of the hull under the surface, from one to nothing.

        The hull is treated as a box of its own height, so it goes from wholly
        under to wholly out over its own depth rather than all at once. A
        vehicle that loses all its buoyancy in one step leaves at speed.
        """
        if level is None:
            return 1.0
        top_of_hull = float(self.position[2]) + self.half_height
        if top_of_hull <= level:
            return 1.0
        under = level - (float(self.position[2]) - self.half_height)
        return float(max(0.0, min(1.0, under / max(1e-6, 2.0 * self.half_height))))


def turn(small: np.ndarray) -> np.ndarray:
    """The rotation for a small rotation vector, by Rodrigues, renormalised so
    that a long dive does not drift off orthonormal."""
    angle = float(np.linalg.norm(small))
    if angle < 1e-12:
        return np.eye(3)
    k = small / angle
    K = np.array([[0.0, -k[2], k[1]],
                  [k[2], 0.0, -k[0]],
                  [-k[1], k[0], 0.0]])
    R = np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)
    u, _, vt = np.linalg.svd(R)
    return u @ vt


def level_facing(way) -> np.ndarray:
    """A rotation that points the nose along `way` (horizontal), level."""
    yaw = math.atan2(float(way[1]), float(way[0]))
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class VehicleSystem(System):
    name = "vehicle"
    reads = ("thrust", "water", "helm", "place")
    before = ("clock", "cable", "coral")
    writes = ("vehicle", "contacts")

    def __init__(self, dt: float, say, attach=(0.0, 0.0, 0.0), weathervanes: bool = False) -> None:
        self.dt = float(dt)
        self.say = say
        # A towfish's fins point it into the flow; it has no say in where it
        # goes, only in how it hangs there.
        self.weathervanes = bool(weathervanes)
        # Where the cable is tied on the hull, body frame: where its pull acts.
        self.attach = np.asarray(attach, dtype=float)

    def step(self, world) -> None:
        v, water, dt = world.vehicle, world.water, self.dt
        body = v.body
        # A vehicle that is not moved by thrust is moved by this: the pump and
        # the sliding mass get a step towards whatever the controller asked
        # for, before the water is asked what it does about it.
        actuators = getattr(world.helm, "actuators", None)
        if actuators is not None:
            body.model.ask_actuators(actuators, dt)
        # How much of the hull is under the surface. Everything the water does
        # is only true of the part that is in it.
        submerged = v.submerged(water.level)

        # Drag is on the motion through the water: the current and the waves'
        # orbits, in the body frame, are taken off the ground velocity first.
        through_water = v.velocity.copy()
        through_water[:3] -= v.rotation.T @ (water.current + water.orbital(
            v.position, v.half_height, world.clock.simulated))
        here = float(-v.position[2])
        wrench = body.step(v.rotation, through_water, world.thrust.commands, dt, submerged,
                           depth_m=here, temperature_c=water.temperature_at(here),
                           density=water.density_at(here))
        v.wrench = wrench
        # And the cable, if there is one out: its pull, in the world frame,
        # turned into the body, acting where it is tied on — so a cable caught
        # behind the vehicle holds it back and pitches it (systems/tether.py).
        cable = world.cable
        if cable is not None and cable.out:
            pulled = v.rotation.T @ cable.force
            wrench[:3] = wrench[:3] + pulled
            wrench[3:] = wrench[3:] + np.cross(self.attach, pulled)

        effective = v.effective if submerged >= 1.0 else body.effective_mass(submerged)
        v.velocity[:3] += (wrench[:3] / effective[:3]) * dt
        v.velocity[3:] += (wrench[3:] / effective[3:]) * dt
        v.position += v.rotation @ v.velocity[:3] * dt
        v.rotation = v.rotation @ turn(v.velocity[3:] * dt)
        if self.weathervanes:
            self.into_the_flow(v, water)

        v.against_the_ground = False
        contact.land(v, world.place, world.contacts, cable, dt, self.say, coral=world.coral)

    @staticmethod
    def into_the_flow(v, water) -> None:
        """Nose into the water going past, level — what a towfish's tail fins
        do (assumed: at once, and fully). Its velocity is kept; only how it is
        described in the body frame changes, and it does not spin."""
        moving = v.rotation @ v.velocity[:3] - water.current
        if float(np.hypot(moving[0], moving[1])) < 0.1:
            return
        world_velocity = v.rotation @ v.velocity[:3]
        v.rotation = level_facing(moving)
        v.velocity[:3] = v.rotation.T @ world_velocity
        v.velocity[3:] = 0.0
