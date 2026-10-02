"""Sand the wash lifts, against the relations the sediment model is built from."""

import math

import numpy as np

from engine import Clock
from systems.coral import Colonies
from systems.place import Place
from systems.sediment import GRAINS, Sediment, SedimentSystem, critical, settling
from systems.vehicle import Vehicle
from systems.wash import Wash
from systems.water import Water

BED = -1.0


class Flat:
    def under_many(self, x, y):
        return np.full(len(np.atleast_1d(x)), BED)

    def normal_many(self, x, y):
        return np.tile([0.0, 0.0, 1.0], (len(np.atleast_1d(x)), 1))

    def under(self, x, y):
        return BED


class Body:
    def effective_mass(self, submerged=1.0):
        return np.ones(6)


def a_world(height, efflux=2.6):
    """A vehicle `height` metres over sand, one thruster driving its wash
    straight down into it."""
    class World:
        pass

    w = World()
    w.clock, w.place, w.water, w.coral, w.sediment = Clock(0.05), Place(), Water(), Colonies(), Sediment()
    w.place.seabed = Flat()
    w.vehicle = Vehicle(Body(), [0.0, 0.0, BED + height])
    w.wash = Wash()
    w.wash.origin = np.array([[0.0, 0.0, BED + height]])
    w.wash.axis = np.array([[0.0, 0.0, -1.0]])
    w.wash.efflux = np.array([efflux])
    w.wash.diameter = 0.038
    return w


def run(world, seconds, system=None):
    system = system or SedimentSystem(0, lambda *a, **k: None)
    for _ in range(int(seconds / 0.05)):
        system.step(world)
        world.clock.simulated += 0.05
    return system


def test_the_settling_speeds_are_ferguson_and_churchs():
    """About 2–3 cm/s for fine sand and a fraction of a millimetre for silt."""
    assert 0.02 < settling(0.25e-3) < 0.04
    assert 0.0002 < settling(0.03e-3) < 0.001


def test_the_thresholds_are_soulsby_and_whitehouses():
    """Fine sand starts to move at about 0.15–0.2 Pa (derived from the curve)."""
    assert 0.12 < critical(0.25e-3) < 0.22


def test_a_thruster_driven_into_the_sand_lifts_it():
    world = a_world(0.04)
    run(world, 1.0)
    assert world.sediment.lifted_kg > 0.0
    assert len(world.sediment.kg) > 0


def test_hovering_half_a_metre_up_lifts_nothing():
    """A jet that has spread and slowed to a tenth of a metre a second over
    the bed is under the threshold."""
    world = a_world(0.5, efflux=0.8)
    run(world, 2.0)
    assert world.sediment.lifted_kg < 1e-6, "under a milligram"


def test_the_sand_falls_back_and_the_silt_hangs():
    world = a_world(0.04)
    system = run(world, 1.0)
    world.wash.efflux = np.zeros(1)              # the thruster stops
    run(world, 6.0, system)
    left = world.sediment.grain
    assert (left == 1).sum() > 5 * max(1, (left == 0).sum()), "silt outlasts sand in the water"
    assert world.sediment.settled_kg > 0.0


def test_a_cloud_in_front_of_the_camera_shortens_what_it_sees():
    world = a_world(0.04)
    clear = SedimentSystem(0, lambda *a, **k: None)
    clear.see(world.sediment, world.vehicle)
    before = world.sediment.visibility_m
    world.sediment.at = np.tile(world.vehicle.position + np.array([0.25, 0.0, 0.0]), (400, 1))
    world.sediment.grain = np.ones(400, dtype=int)
    world.sediment.kg = np.full(400, 2e-6)
    clear.see(world.sediment, world.vehicle)
    assert world.sediment.visibility_m < 0.5 * before


def test_what_lands_on_a_colony_is_counted_against_it():
    world = a_world(0.04)
    coral = Colonies()
    coral.at = np.array([[0.0, 0.0, BED]])
    coral.size = np.array([0.2])
    coral.kind = np.array(["branching"], dtype=object)
    coral.height = coral.size.copy()
    world.coral = coral
    SedimentSystem.on_the_coral(world.sediment, coral, np.array([[0.0, 0.0, BED]]), np.array([1e-3]))
    assert world.sediment.on_coral_mg_cm2[0] > 0.0
