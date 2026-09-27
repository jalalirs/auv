"""Hold station — depth, heading and position — written against the SDK.

The same class runs in the tank on a laptop, on the platform over ROS 2, and on
a vehicle. It asks for a wrench in newtons and lets the vehicle allocate it,
sizes its gains by the vehicle's own mass, and feeds forward the trim the
catalogue declares — the three things the runtime's own hold does.

    coral-city tank examples/hold.py --task hold --trace
    coral-city deploy examples/hold.py --slug hold --name "Depth and heading hold"
"""

from __future__ import annotations

import math

import numpy as np

from coral_city import Command, Controller, Observation


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class StationHold(Controller):
    name = "station-hold"
    says = "Holds the depth and heading it was engaged at, or the ones you set."
    vehicle = "bluerov2"
    commands = "wrench"
    needs = ("dvl",)

    def __init__(self) -> None:
        super().__init__()
        self.declare("depthM", 0.0, 0.0, 100.0, "m", "the depth to hold; 0 means where it was engaged")
        self.declare("headingDeg", 0.0, -180.0, 180.0, "°", "the heading to hold")
        self.declare("depthKp", 0.5, 0.0, 3.0, "1/s²", "heave per metre of depth error")
        self.declare("depthKd", 1.4, 0.0, 6.0, "1/s", "heave against vertical speed")
        self.declare("headingKp", 2.0, 0.0, 10.0, "1/s²", "yaw per radian of heading error")
        self.declare("headingKd", 2.8, 0.0, 10.0, "1/s", "yaw against turn rate")
        self.declare("positionKp", 0.4, 0.0, 3.0, "1/s²", "surge and sway per metre off station")
        self.declare("positionKd", 1.3, 0.0, 6.0, "1/s", "surge and sway against speed over the ground")
        self.declare("positionKi", 0.30, 0.0, 1.5, "1/s³",
                     "surge and sway per metre-second off station: what holds against a current")
        self.declare("carryM", 20.0, 0.0, 60.0, "m·s",
                     "how much error it will carry before it stops adding more")
        # The vehicle's own figures, from the catalogue: how heavy it is to
        # accelerate, and how many newtons of heave make it neutral.
        dynamics = self.described.dynamics
        added = dynamics["addedMass"]["diagonal"]
        inertia = dynamics.get("inertiaTensor", [0.1] * 9)
        self.heave_mass = dynamics["massKg"] + abs(added[2])
        self.surge_mass = dynamics["massKg"] + abs(added[0])
        self.sway_mass = dynamics["massKg"] + abs(added[1])
        self.yaw_inertia = abs(inertia[8]) + abs(added[5])
        self.trim_n = -self.described.net_buoyancy_n
        self.station = None
        # What it has carried, in metre-seconds, body frame. This is the whole
        # difference between holding in still water and holding in a current: a
        # proportional term settles where its own push balances the drag, which is
        # *off station* by exactly however far that takes. Measured before it was
        # The first values tried here were Ki 0.06 and a 6 m·s cap, and the cap
        # pinned: the hold sat 0.58 m off a 0.5 m radius asking 11 N of a 145 N
        # envelope — nowhere near saturated — with `carried` clamped flat. Loosening
        # it is worth six times the score at one knot (0.092 → 0.560); raising the
        # proportional gain instead is worth 0.182, so it is the integral doing the
        # work and not the gain.
        #
        # here: 1.000 in still water, 0.094 at one knot, 0.040 at two, against the
        # runtime's own hold at 100% in all four — and this repository had recorded
        # that as a limit of the vehicle since 3 September. It was a missing integral.
        self.carried = np.zeros(2)
        self.last_t: float | None = None

    def engage(self, seen: Observation) -> None:
        if self["depthM"] == 0.0:
            self.parameters["depthM"].set(seen.depth)
        self.parameters["headingDeg"].set(math.degrees(seen.heading))
        # Where it is, as it reckons it: on a vehicle that is the DVL's word
        # for it, and holding station means holding that.
        self.station = seen.position[:2].copy()
        self.carried = np.zeros(2)
        self.last_t = None

    def observe(self, seen: Observation) -> Command:
        most = self.described.most
        # Depth: positive error is too deep; rising closes it.
        error = seen.depth - self["depthM"]
        heave = self.heave_mass * (self["depthKp"] * error - self["depthKd"] * seen.velocity[2]) + self.trim_n
        turn = wrap(math.radians(self["headingDeg"]) - seen.heading)
        yaw = self.yaw_inertia * (self["headingKp"] * turn - self["headingKd"] * seen.velocity[5])
        # Off station, in the body frame, so the correction is a surge and a sway.
        off_world = self.station - seen.position[:2] if self.station is not None else (0.0, 0.0)
        off_body = seen.rotation.T @ (float(off_world[0]), float(off_world[1]), 0.0)
        # How long since the last look, from the dive's own clock rather than the
        # machine's, so the same controller integrates the same way in a tank running
        # flat out and on a vehicle running in real time.
        gap = 0.0 if self.last_t is None else max(0.0, float(seen.t) - self.last_t)
        self.last_t = float(seen.t)
        self.carried += np.array([off_body[0], off_body[1]]) * gap
        # Capped, and that is not decoration: a vehicle held off station by something
        # it cannot beat — a current past its thrust, a snagged tether — would
        # otherwise wind this up without limit and then slam the other way when it
        # came free.
        carry = float(self["carryM"])
        if carry > 0.0:
            self.carried = np.clip(self.carried, -carry, carry)
        else:
            self.carried[:] = 0.0
        surge = self.surge_mass * (self["positionKp"] * off_body[0]
                                   + self["positionKi"] * self.carried[0]
                                   - self["positionKd"] * seen.velocity[0])
        sway = self.sway_mass * (self["positionKp"] * off_body[1]
                                 + self["positionKi"] * self.carried[1]
                                 - self["positionKd"] * seen.velocity[1])
        return Command.wrench_of(
            surge=max(-most[0], min(most[0], surge)),
            sway=max(-most[1], min(most[1], sway)),
            heave=max(-most[2], min(most[2], heave)),
            yaw=max(-most[5], min(most[5], yaw)),
        )

    def status(self) -> dict:
        return {"trimN": round(self.trim_n, 2),
                "station": None if self.station is None else [round(float(v), 2) for v in self.station],
                "carriedMs": [round(float(v), 2) for v in self.carried]}
