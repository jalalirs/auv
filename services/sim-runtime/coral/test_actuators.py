"""A vehicle that is not moved by thrust.

Every controller here answered with a wrench or with thruster commands, and
everything between a controller and the water assumed one of the two. A
buoyancy glider takes neither: it is told how much water to displace and where
to put its mass, and its wings turn falling into going somewhere. A platform
whose only two answers are force has quietly decided what a vehicle is.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Hydrodynamics

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"

GLIDER = {"vbdCcRange": [-400.0, 400.0], "vbdRateCcPerS": 5.0,
          "massShiftM": 0.03, "massRollM": 0.02, "massRateMPerS": 0.01,
          "massShiftKg": 9.0}


def a_glider():
    model = Hydrodynamics.from_package(PACKAGE)
    model.mass_kg = 52.0
    model.displaced_volume_m3 = 0.0507
    model.commanded_in = "buoyancy"
    model.actuators = dict(GLIDER)
    return model


def test_a_vehicle_that_says_nothing_is_commanded_in_a_wrench():
    """What every vehicle in the catalogue is, and must go on being."""
    model = Hydrodynamics.from_package(PACKAGE)
    assert model.commanded_in == "wrench"
    assert model.actuators == {}
    assert model.vbd_m3 == 0.0


def test_the_pump_has_a_rate_and_the_dive_cycle_is_made_of_it():
    """A buoyancy engine that answered instantly would let a glider stop dead
    in the water column, which is the one thing it cannot do."""
    model = a_glider()
    model.ask_actuators({"vbdCc": 400.0}, dt=1.0)
    assert abs(model.vbd_m3 * 1e6 - 5.0) < 1e-9, "five cc in the first second, not four hundred"
    for _ in range(200):
        model.ask_actuators({"vbdCc": 400.0}, dt=1.0)
    assert abs(model.vbd_m3 * 1e6 - 400.0) < 1e-6, "and all of it eventually"


def test_the_pump_will_not_go_past_what_the_package_says_it_has():
    model = a_glider()
    for _ in range(500):
        model.ask_actuators({"vbdCc": 10_000.0}, dt=1.0)
    assert abs(model.vbd_m3 * 1e6 - 400.0) < 1e-6


def test_displacing_more_water_makes_it_float():
    model = a_glider()
    neutral = model.buoyancy_n_at(0.0)
    for _ in range(200):
        model.ask_actuators({"vbdCc": 400.0}, dt=1.0)
    assert model.buoyancy_n_at(0.0) > neutral
    # Four hundred cc of seawater is about four newtons, which on a
    # fifty-kilogram vehicle is the whole of its propulsion.
    assert 3.9 < model.buoyancy_n_at(0.0) - neutral < 4.2


def test_sliding_the_battery_moves_the_whole_vehicles_centre_of_gravity():
    """How a glider pitches: nine kilos moving three centimetres on a
    fifty-two kilogram hull."""
    model = a_glider()
    built = model.centre_of_gravity_now().copy()
    for _ in range(100):
        model.ask_actuators({"pitchM": -0.03}, dt=1.0)
    moved = model.centre_of_gravity_now()
    assert moved[0] < built[0], "mass aft, nose up"
    assert abs((built[0] - moved[0]) - 0.03 * 9.0 / 52.0) < 1e-6


def test_a_hull_with_no_moving_mass_does_not_pretend_to_have_one():
    model = Hydrodynamics.from_package(PACKAGE)
    model.mass_shift_m = np.array([0.5, 0.5, 0.0])
    assert np.allclose(model.centre_of_gravity_now(), model.centre_of_gravity)
