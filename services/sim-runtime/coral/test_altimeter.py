"""The altimeter reads the first thing under the vehicle: over a reef, a colony's top."""

import numpy as np

from engine import Clock
from systems.coral import Colonies, _fresh
from systems.helm import observe
from systems.place import Place

BED = -12.0


class Flat:
    def under(self, x, y):
        return BED


class Still:
    def __init__(self, at):
        self.position = np.array(at, dtype=float)
        self.velocity = np.zeros(6)
        self.rotation = np.eye(3)
        self.on_the_bottom = False


def a_colony_four_metres_tall(vehicle_at):
    class Ocean:
        pass

    o = Ocean()
    o.clock, o.place = Clock(0.05), Place()
    o.place.seabed = Flat()
    o.navigation, o.sonar = None, None
    o.vehicle = Still(vehicle_at)
    c = Colonies()
    c.at = np.array([[0.0, 0.0, BED]])
    c.size = np.array([4.0])
    c.kind = np.array(["massive"], dtype=object)
    c.prim = [None]
    c.height = c.size.copy()
    _fresh(c, 1)
    o.coral = c
    return o


def test_over_a_colony_the_bottom_is_its_top():
    seen = observe(a_colony_four_metres_tall([0.5, 0.0, -5.0]))
    assert abs(seen.floor - (BED + 4.0)) < 1e-9


def test_beside_it_the_bottom_is_the_sand():
    seen = observe(a_colony_four_metres_tall([20.0, 0.0, -5.0]))
    assert seen.floor == BED


def test_a_colony_above_the_vehicle_is_not_under_it():
    seen = observe(a_colony_four_metres_tall([0.5, 0.0, -10.0]))
    assert seen.floor == BED
