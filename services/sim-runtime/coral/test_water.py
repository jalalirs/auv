"""Water that has a density, and a depth gauge that was set for a different sea.

Density was a constant in the runtime and an argument to the vehicle's
constructor, which put the water's own property inside the vehicle. A dive
could not ask for different water, so Florida and the Red Sea were the same
sea and the difference between them — four kilos a cubic metre, a fifth of
what our BlueROV2 is out of trim by — did not exist.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import DENSITY_SEAWATER, Allocator, Body, Hydrodynamics, density_of  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"

LOOE_KEY = {"salinityPsu": 36.0, "temperatureC": 29.0}
RED_SEA = {"salinityPsu": 40.6, "temperatureC": 26.0}


def a_dive(water):
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 120, "initialState": {"positionM": [0, 0, -7]},
             "conditions": {"kind": "constructed", "parameters": water}}
    return Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)


def test_the_equation_of_state_is_the_published_one():
    """EOS-80 verbatim, against the check values in the tables.

    Worth testing rather than trusting, because the whole point of carrying the
    real equation is a difference of four kilos a cubic metre, and an equation
    that is wrong by four is indistinguishable from the constant it replaced.
    """
    for salinity, temperature, published in ((0.0, 5.0, 999.96675),
                                             (35.0, 0.0, 1028.10623),
                                             (35.0, 20.0, 1024.76346),
                                             (35.0, 25.0, 1023.34306)):
        got = density_of(salinity, temperature)
        assert abs(got - published) < 1e-3, f"S={salinity} T={temperature}: {got} not {published}"


def test_water_that_says_nothing_floats_a_vehicle_the_way_it_always_did():
    """No silent re-pricing of every dive already in the record."""
    dive = a_dive({})
    assert dive.density == DENSITY_SEAWATER
    assert dive.body.model.density == DENSITY_SEAWATER


def test_the_same_hull_floats_differently_in_two_real_seas():
    florida, red_sea = a_dive(LOOE_KEY), a_dive(RED_SEA)
    assert red_sea.density > florida.density
    assert abs((red_sea.density - florida.density) - 4.45) < 0.1, "the gap between the two sites"

    # What that is worth to the vehicle: buoyancy is density times displaced
    # volume times g, and the vehicle's whole trim is under two newtons.
    heavier = florida.body.model.net_buoyancy_n
    lighter = red_sea.body.model.net_buoyancy_n
    assert lighter > heavier, "saltier water holds it up better"
    assert abs(lighter - heavier) > 0.4, "and by enough to matter against a 1.9 N trim"


def test_a_measured_density_is_not_second_guessed():
    dive = a_dive({"salinityPsu": 40.6, "temperatureC": 26.0, "densityKgM3": 1031.0})
    assert dive.density == 1031.0


def test_a_depth_gauge_set_for_the_wrong_sea_is_wrong_in_proportion():
    """Biased, not noisy: the same fraction wrong at every depth.

    A gauge calibrated on shore for ordinary seawater and flown in the Red Sea
    divides the pressure it feels by too small a number, so it reads deep —
    and it reads further deep the deeper the vehicle goes, which is the
    opposite of how every other error in this platform behaves.
    """
    dive = a_dive({**RED_SEA, "depthGaugeDensityKgM3": DENSITY_SEAWATER})
    scale = dive.density / dive.depth_gauge_density
    assert scale > 1.0, "the Red Sea is denser than the gauge was told"
    for depth in (10.0, 50.0, 100.0):
        assert 0.0 < depth * (scale - 1.0) < 0.5
    assert abs(100.0 * (scale - 1.0) - 0.22) < 0.05, "about a fifth of a metre at a hundred"

    # And a gauge that suits its water is not wrong at all.
    honest = a_dive(RED_SEA)
    assert honest.depth_gauge_density == honest.density


def test_the_dive_says_what_water_it_was_in():
    said = a_dive({**RED_SEA, "depthGaugeDensityKgM3": DENSITY_SEAWATER}).conditions_said()
    assert said["salinityPsu"] == 40.6
    assert said["temperatureC"] == 26.0
    assert abs(said["densityKgM3"] - 1027.27) < 0.01
    assert said["depthGaugeDensityKgM3"] == DENSITY_SEAWATER
    # A gauge that matches its water is not worth a line.
    assert "depthGaugeDensityKgM3" not in a_dive(RED_SEA).conditions_said()
