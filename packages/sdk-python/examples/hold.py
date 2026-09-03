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

    def engage(self, seen: Observation) -> None:
        if self["depthM"] == 0.0:
            self.parameters["depthM"].set(seen.depth)
        self.parameters["headingDeg"].set(math.degrees(seen.heading))
        # Where it is, as it reckons it: on a vehicle that is the DVL's word
        # for it, and holding station means holding that.
        self.station = seen.position[:2].copy()

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
        surge = self.surge_mass * (self["positionKp"] * off_body[0] - self["positionKd"] * seen.velocity[0])
        sway = self.sway_mass * (self["positionKp"] * off_body[1] - self["positionKd"] * seen.velocity[1])
        return Command.wrench_of(
            surge=max(-most[0], min(most[0], surge)),
            sway=max(-most[1], min(most[1], sway)),
            heave=max(-most[2], min(most[2], heave)),
            yaw=max(-most[5], min(most[5], yaw)),
        )

    def status(self) -> dict:
        return {"trimN": round(self.trim_n, 2),
                "station": None if self.station is None else [round(float(v), 2) for v in self.station]}
