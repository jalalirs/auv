"""A dredger's plume: lost at its overflow, carried by the current, settled on the reef."""

import numpy as np

from engine import Clock
from systems.coral import Colonies, _fresh, dose_per_day
from systems.place import Place
from systems.sediment import Sediment, SedimentSystem
from systems.vehicle import Vehicle
from systems.wash import Wash
from systems.water import Water
from world import World

BED = -8.0


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


def a_reef_and_a_dredger(current=(0.2, 0.0, 0.0)):
    """A dredger at the origin and two big colonies on the bed, one sixty
    metres down-current of it and one sixty up."""
    class Ocean:
        pass

    o = Ocean()
    o.clock, o.place, o.water, o.sediment = Clock(0.05), Place(), Water(), Sediment()
    o.place.seabed = Flat()
    o.place.things = World({"things": [{"id": "dredger-1", "kind": "dredger", "x": 0.0, "y": 0.0,
                                        "releaseKgPerS": 20.0, "releaseDepthM": 2.0}]})
    o.water.current = np.array(current, dtype=float)
    o.vehicle = Vehicle(Body(), [500.0, 500.0, -2.0])
    o.wash = Wash()
    c = Colonies()
    c.at = np.array([[60.0, 0.0, BED], [-60.0, 0.0, BED]])
    c.size = np.array([3.0, 3.0])
    c.kind = np.array(["massive", "massive"], dtype=object)
    c.prim = [None, None]
    c.height = c.size.copy()
    _fresh(c, 2)
    o.coral = c
    return o


def test_the_plume_settles_down_current_and_not_up():
    ocean = a_reef_and_a_dredger()
    system = SedimentSystem(0, lambda *a, **k: None)
    for _ in range(int(600 / 0.05)):
        system.step(ocean)
        ocean.clock.simulated += 0.05
    sed = ocean.sediment
    assert abs(sed.dredged_kg - 20.0 * 600) < 1.0, "it loses what it is said to lose"
    dose = dose_per_day(sed.on_coral_mg_cm2, 600.0)
    assert dose[0] > 0.0, "the colony down-current is dosed"
    assert dose[1] == 0.0, "the colony up-current is not"
    assert sed.said()["dredgedKg"] > 0
