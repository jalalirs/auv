"""The systems a dive is made of, one file each.

Each file holds a system and the part of the world it owns, and opens with
what it reads, what it writes, and where its model comes from. The order they
run in is not written anywhere: the engine works it out from those
declarations (engine/schedule.py), and `tools/regress` holds it to the dives it
flew before each move.

    faults        what the dive was told would go wrong, and when
    light         the day: the hour, and the sun or a tank's lights
    water         the water's motion: current, wind drift, the waves' orbits
    views         which camera a dive that asked for several is on
    navigation    where the vehicle believes it is
    instruments   the CTD, the water-quality sonde, the multibeam and the imaging sonar
    helm          what the controller commands, on what it knows
    thrusters     what the thrusters actually do with it: failures, the battery
    vehicle       the hull moved by its thrusters, the water and its cable
    contact       the ground, the glass and what is in the water, stopping it
    wash          the jet of water behind every thruster that is pushing
    fish          every fish, each with a mind: schooling, foraging, fleeing
    coral         colonies that stop the vehicle, and break when they should
    tether        the cable: moving, caught on things, failing the dive
    sediment      sand the wash lifts, the water carries and the camera sees through
    tow           a ship towing: her stern is the tow cable's dry end
    sidescan      a towfish's side-scan: the seabed either side, by slant range, with shadows
    tasking       the task: planned, scored, and whether the dive is over
    outputs       the ROS 2 bridge and the record

`build.py` assembles them for a dive.

**Adding one.** A system is a class with four things and a step:

    class Barnacles(System):
        name = "barnacles"
        reads = ("vehicle", "clock")          # after whatever writes these
        before = ("water",)                   # as the tick found it
        writes = ("barnacles",)               # yours, and only yours
        every = 1.0                           # seconds of the dive; None is every tick

        def step(self, world):
            ...                               # read world.vehicle, write world.barnacles

Then, in build.py, put its part in `the_ocean` with its owner
(`world.put("barnacles", Barnacles(), owner="barnacles")`) and the system in
`the_systems`. The engine works out where it runs from what it reads and
writes, and refuses — naming the loop — a declaration that makes one. Test it
on its own, against the published numbers it is built from; then run
tools/regress, which says whether the reference dives still fly the same.

What a system must not do: call another system, write a part it does not
own, or reach into the dive (`runner.Dive`). What it needs, it reads from the
world; what others need from it, it writes there.
"""
