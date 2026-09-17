"""A glider sawtooth, written against the SDK.

Thirty lines of decision and a great deal of waiting, which is what flying a
buoyancy glider is. There is no throttle here and no wrench: the vehicle is
told how much water to displace and where to put its mass, and its wings turn
falling into going somewhere.

This is the example that could not be written until now. The SDK exposed a
wrench and thruster commands and nothing else, so the vehicle this whole phase
was built around was closed to exactly the people whose controllers are
supposed to be the point — somebody outside this repository could fly a
BlueROV2 and could not fly a Seaglider at all.

    coral-city check examples/sawtooth.py
    coral-city tank examples/sawtooth.py --task profile --trace

What to expect: a dive cycle measured in tens of minutes rather than seconds.
The pump moves a few cubic centimetres a second and the vehicle takes as long
as it takes to answer, which is why a glider pilot's loop is measured in hours
and why the science that comes back is a profile.
"""

from __future__ import annotations

from coral_city import Command, Controller, Observation


class Sawtooth(Controller):
    name = "sawtooth"
    says = "Falls and climbs between two depths, on buoyancy and a sliding mass."
    vehicle = "seaglider"
    # The third form. A hull with no propeller takes neither a wrench nor
    # thruster commands; it takes its own actuators, by the names its package
    # declares — `coral-city vehicles` says which, and what their limits are.
    commands = "actuators"
    needs = ("ctd",)

    def __init__(self) -> None:
        super().__init__()
        self.declare("topM", 15.0, 2.0, 200.0, "m", "the shallow end of the sawtooth")
        self.declare("bottomM", 300.0, 20.0, 900.0, "m", "the deep end of it")
        self.declare("pumpCc", 220.0, 50.0, 400.0, "cm³",
                     "how much water it moves to change its mind")
        self.declare("pitchM", 0.022, 0.0, 0.035, "m",
                     "how far the battery slides to set the angle")
        # Which way it is going. A glider's whole state, very nearly.
        self.falling = True

    def observe(self, seen: Observation) -> Command:
        # Turn at the ends of the band and nowhere else. A glider that changed
        # its mind on the way would spend its endurance pumping, and the pump
        # is most of what it spends.
        if self.falling and seen.depth >= self["bottomM"]:
            self.falling = False
        elif not self.falling and seen.depth <= self["topM"]:
            self.falling = True

        # Heavy and nose-down to fall, light and nose-up to climb. The wings
        # do the rest, and the rest is the whole vehicle.
        if self.falling:
            return Command.actuators_of(vbdCc=-self["pumpCc"], pitchM=self["pitchM"])
        return Command.actuators_of(vbdCc=self["pumpCc"], pitchM=-self["pitchM"])
