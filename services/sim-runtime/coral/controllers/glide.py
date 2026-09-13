"""Flying a glider: a sawtooth, made of buoyancy and a sliding battery.

There is no throttle here and no wrench. The whole of what this controller does
is decide whether the vehicle should be heavy or light and which way its nose
should point, and then wait — because the pump moves a few cubic centimetres a
second and the vehicle takes as long as it takes to answer. A glider pilot's
loop is measured in hours for the same reason.

The pattern is the one every buoyancy glider has flown since the first of them:
pump water in, nose down, and fall forward on the wings until the bottom of the
band; pump it out, nose up, and climb the same way. Down and up, over and over,
which is why the track through the water is called a sawtooth and why the
science that comes back is a profile.

What it cannot do matters as much as what it can. It cannot stop: a glider that
stops flying falls out of the water column, and there is no station-keeping in
it anywhere. It cannot hold a depth. It cannot fight much of a current — a
Seaglider makes about a quarter of a metre a second, so anything much over
0.4 m/s carries it away and the only thing to do about it is point somewhere
else and accept where you end up.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Controller, Observation


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class GlideController(Controller):
    """Dive and climb between two depths, holding a heading as well as it can."""

    name = "glide"
    kind = "builtin"
    says = "Flies a buoyancy glider: down and up between two depths, on the wings."

    def __init__(self, dt: float) -> None:
        super().__init__()
        self.dt = dt
        d = self.declare
        d("diveToM", 200.0, 1.0, 1000.0, "m", "how deep it goes before turning round")
        d("climbToM", 10.0, 0.0, 500.0, "m", "how shallow it comes before going down again")
        d("vbdCc", 250.0, 10.0, 400.0, "cc", "how much displacement it uses, either way")
        d("pitchM", 0.025, 0.0, 0.05, "m", "how far the mass slides to set the glide angle")
        d("rollM", 0.012, 0.0, 0.03, "m", "how far it rolls to turn")
        d("headingKp", 0.6, 0.0, 4.0, "1/rad", "roll per radian of heading error")
        # Which way it is going. A glider is always doing one or the other:
        # there is no third state where it holds still.
        self.descending = True
        self.legs = 0
        self.heading_wanted: float | None = None
        self.deepest = 0.0
        self.shallowest = 1e9

    def engage(self, seen: Observation) -> None:
        self.heading_wanted = seen.heading if self.heading_wanted is None else self.heading_wanted
        self.descending = seen.depth < float(self["diveToM"])
        self.deepest, self.shallowest = seen.depth, seen.depth

    def steer(self, heading_rad: float | None) -> None:
        """Point somewhere. The only steering a glider has."""
        self.heading_wanted = None if heading_rad is None else wrap(float(heading_rad))

    def tasked(self, goal: dict) -> None:
        super().tasked(goal)
        band = goal.get("bandM")
        if isinstance(band, (list, tuple)) and len(band) == 2:
            self.tune("climbToM", float(min(band)))
            self.tune("diveToM", float(max(band)))

    def observe(self, seen: Observation) -> Command:
        depth = seen.depth
        self.deepest = max(self.deepest, depth)
        self.shallowest = min(self.shallowest, depth)
        # The turn, at the ends of the band. One counted leg is half a
        # sawtooth, because that is the unit a glider's science comes in.
        if self.descending and depth >= float(self["diveToM"]):
            self.descending = False
            self.legs += 1
        elif not self.descending and depth <= float(self["climbToM"]):
            self.descending = True
            self.legs += 1

        displacement = float(self["vbdCc"])
        slide = float(self["pitchM"])
        # Heavy and nose down to descend; light and nose up to climb. The sign
        # of one has to match the sign of the other or the wing is on the wrong
        # side of the flow and the vehicle slides backwards.
        vbd = -displacement if self.descending else displacement
        pitch = slide if self.descending else -slide

        roll = 0.0
        if self.heading_wanted is not None:
            error = wrap(self.heading_wanted - seen.heading)
            roll = float(np.clip(error * float(self["headingKp"]),
                                 -float(self["rollM"]), float(self["rollM"])))
        return Command(actuators={"vbdCc": vbd, "pitchM": pitch, "rollM": roll})

    def status(self) -> dict:
        return {"doing": "descending" if self.descending else "climbing",
                "legs": self.legs,
                "deepestM": round(self.deepest, 1),
                "shallowestM": round(self.shallowest, 1),
                "headingWantedDeg": (None if self.heading_wanted is None
                                     else round(math.degrees(self.heading_wanted), 1))}
