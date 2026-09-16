"""What a vehicle carries, and what it costs to carry it.

The hotel load was one number standing for the electronics, the sensors and the
lights together, so a dive that unshipped a Doppler log or flew with the lamps
off lasted exactly as long as one that did not. That made `fitted` a label
rather than a choice, and made the endurance in every cost estimate the
endurance of a fully laden vehicle whatever anybody chose.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

CATALOG = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles"


def a_package(name):
    return json.loads((CATALOG / name / "dynamics.json").read_text())


def test_every_instrument_says_what_it_draws():
    """A sensor with no draw is a sensor that is free to carry, and none is."""
    for name in ("bluerov2", "bluerov2-heavy", "remus-100", "seaglider"):
        for one in a_package(name).get("sensors", []):
            assert one.get("watts") is not None, f"{name}: {one.get('kind')} draws nothing"


def test_the_hotel_load_is_the_electronics_and_not_everything():
    """It used to be the lump. If it is still the lump, the instruments are
    being counted twice and unfitting one changes nothing."""
    d = a_package("bluerov2")
    base = float(d["power"]["hotelW"])
    sensors = sum(float(one.get("watts", 0.0)) for one in d.get("sensors", []))
    assert base < sensors, f"base {base} W should be less than {sensors:.1f} W of sensors"


def test_a_vehicle_says_what_it_thinks_with():
    """And a hull that cannot run a network says so before the dive rather
    than after it."""
    for name in ("bluerov2", "bluerov2-heavy", "remus-100", "seaglider"):
        machine = a_package(name).get("computer")
        assert machine is not None, f"{name} has no computer"
        assert machine.get("watts") is not None
        assert machine.get("tops") is not None


def test_the_heavy_can_think_and_the_stock_hull_cannot():
    """The difference that decides whether a vision stack is deployable: a
    Raspberry Pi will run a PID loop and will not run a network."""
    assert a_package("bluerov2")["computer"]["tops"] == 0.0
    assert a_package("bluerov2-heavy")["computer"]["tops"] > 50.0


def test_a_glider_thinks_almost_for_free():
    """Its whole endurance argument is that it thinks slowly and rarely."""
    d = a_package("seaglider")
    assert float(d["computer"]["watts"]) < 0.5
    assert float(d["power"]["hotelW"]) < 1.0
