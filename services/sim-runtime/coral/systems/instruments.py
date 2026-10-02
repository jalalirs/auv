"""The instruments that measure the world: the CTD, the multibeam, the sonar.

Each reads the vehicle and the clock as they were at the start of the tick and
writes only its own reading, at its own rate. The instruments themselves —
how a beam is cast, how noisy it is — are ctd here, multibeam.py and sonar.py.

    ctd          Reads the water.   Writes ctd: the profile of the column.
    multibeam    Reads the place.   Writes multibeam (the instrument) and
                 swath (what it sounded this tick, for the record).
    sonar        Reads the place; the coral and the fish as they were at the
                 start of the tick. Writes sonar (the instrument, whose fan
                 the controller reads) and ping (whether it pinged this tick,
                 for the bridge). What echoes is the ground, the glass, what
                 was put in the water, the stony coral, and the fish — an
                 echosounder hears a fish's swim bladder, which is why a
                 single-beam on a reef sees obstacles that swim away.
"""

from __future__ import annotations

from engine import System


class Ctd:
    def __init__(self) -> None:
        self.config = None           # {"everyS": ...} when the vehicle carries one
        self.profile: list[dict] = []
        self.last_t = None


class Fresh:
    """A reading, and whether it was taken this tick."""

    def __init__(self) -> None:
        self.fresh = False
        self.value = None


class CtdSystem(System):
    """Take a cast, at the instrument's own rate.

    Kept as a profile rather than only published, because the profile *is* the
    deliverable: a section flown by a glider comes home as the column against
    distance, and a monitoring dive that measured the water it worked in can
    say what the water was.
    """

    name = "ctd"
    reads = ("water",)
    before = ("vehicle", "clock")
    writes = ("ctd",)

    def step(self, world) -> None:
        ctd, now = world.ctd, world.clock.simulated
        if ctd.config is None:
            return
        if ctd.last_t is not None and (now - ctd.last_t) < ctd.config["everyS"]:
            return
        ctd.last_t = now
        water, position = world.water, world.vehicle.position
        depth = max(0.0, float(-position[2]))
        ctd.profile.append({
            "t": round(now, 2),
            "depthM": round(depth, 3),
            "temperatureC": None if water.temperature_at(depth) is None
            else round(float(water.temperature_at(depth)), 3),
            "salinityPsu": None if water.salinity in (None, "")
            else round(float(water.salinity), 3),
            "densityKgM3": round(float(water.density_at(depth)), 3),
            "atM": [round(float(position[0]), 1), round(float(position[1]), 1)],
        })


class MultibeamSystem(System):
    name = "multibeam"
    reads = ("place",)
    before = ("vehicle", "clock")
    writes = ("multibeam", "swath")

    def step(self, world) -> None:
        swath = world.swath
        swath.fresh = False
        instrument = world.multibeam
        if instrument is None or not instrument.due(world.clock.simulated):
            return
        vehicle = world.vehicle
        swath.value = instrument.ping(world.clock.simulated, vehicle.position,
                                      vehicle.rotation, world.place.seabed)
        swath.fresh = True


# The smallest fish an echosounder at a few metres picks out of the noise, as a
# body length. Assumed: a few centimetres of fish is a few millimetres of swim
# bladder, which is at the limit of a small single-beam.
SMALLEST_FISH_M = 0.04


def echoes(world) -> "np.ndarray | None":
    """What in the water echoes and is not ground: the stony coral, stacked as
    spheres up each column, and every fish big enough to hear."""
    import numpy as np

    parts = []
    coral = world.coral
    if coral is not None and len(coral):
        solid = np.flatnonzero(coral.solid())
        if len(solid):
            r = coral.radius[solid]
            stack = np.maximum(1, np.floor((coral.height[solid] - r) / np.maximum(r, 0.02)).astype(int) + 1)
            which = np.repeat(np.arange(len(solid)), stack)
            step = np.arange(len(which)) - np.repeat(np.cumsum(stack) - stack, stack)
            i = solid[which]
            z = coral.at[i, 2] + r[which] + step * np.maximum(r[which], 0.02)
            parts.append(np.column_stack([coral.at[i, 0], coral.at[i, 1], z, r[which]]))
    fish = world.fish
    if fish is not None and fish.of_them:
        big = fish.length >= SMALLEST_FISH_M
        if big.any():
            parts.append(np.column_stack([fish.at[big], 0.5 * fish.length[big]]))
    return np.vstack(parts) if parts else None


class SonarSystem(System):
    name = "sonar"
    reads = ("place",)
    before = ("vehicle", "clock", "coral", "fish")
    writes = ("sonar", "ping")

    def step(self, world) -> None:
        ping = world.ping
        ping.fresh = False
        instrument = world.sonar
        if instrument is None or not instrument.due(world.clock.simulated):
            return
        vehicle, place = world.vehicle, world.place
        instrument.ping(world.clock.simulated, vehicle.position, vehicle.rotation,
                        place.things, place.seabed, walls=place.interior, targets=echoes(world))
        ping.fresh = True
