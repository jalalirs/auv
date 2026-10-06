"""A hold goes to its station first; a transect's altitude is judged as the altimeter reads it."""

import numpy as np

from controllers.plan import route_for
from systems.coral import Colonies, _fresh
from systems.helm import what_the_altimeter_sees
from systems.place import Place


def test_a_hold_that_names_its_station_goes_there():
    route = route_for({"kind": "hold", "at": [40.0, -200.0, -0.4], "radiusM": 3.0})
    assert len(route) == 1
    assert (route[0]["x"], route[0]["y"]) == (40.0, -200.0)
    assert abs(route[0]["depthM"] - 0.4) < 1e-9
    assert route[0]["arriveM"] <= 1.5


def test_a_hold_with_nowhere_named_stays_put():
    assert route_for({"kind": "hold"}) == []


def test_tasks_and_vehicle_see_the_same_bottom():
    class Flat:
        def under(self, x, y):
            return -12.0

    class Ocean:
        pass

    o = Ocean()
    o.place = Place()
    o.place.seabed = Flat()
    c = Colonies()
    c.at = np.array([[0.0, 0.0, -12.0]])
    c.size = np.array([4.0])
    c.kind = np.array(["massive"], dtype=object)
    c.prim = [None]
    c.height = c.size.copy()
    _fresh(c, 1)
    o.coral = c
    floor = what_the_altimeter_sees(o, np.array([0.3, 0.0, -5.0]), -12.0)
    assert abs(floor - (-8.0)) < 1e-9, "three metres over the colony is three metres, not seven"
