"""Water that moves: the current carries what does not fight it, and the hold fights it."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"


def a_dive(current):
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 120, "initialState": {"positionM": [0, 0, -7]},
             "conditions": {"kind": "constructed", "parameters": current}}
    return Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)


def test_a_current_is_read_as_a_vector_flowing_towards_its_heading():
    dive = a_dive({"currentMetresPerSecond": 0.5, "currentHeadingDeg": 90.0})   # flows east
    assert np.allclose(dive.current, [0.5, 0.0, 0.0], atol=1e-9)
    said = dive.conditions_said()
    assert said["currentMetresPerSecond"] == 0.5 and said["currentHeadingDeg"] == 90.0
    north = a_dive({"currentMetresPerSecond": 1.0, "currentHeadingDeg": 0.0})
    assert np.allclose(north.current, [0.0, 1.0, 0.0], atol=1e-9)


def test_the_hold_fights_the_current_and_stays_put():
    dive = a_dive({"currentMetresPerSecond": 0.3, "currentHeadingDeg": 90.0})
    for _ in range(int(60 / dive.dt)):
        dive.step()
    off = float(np.hypot(dive.position[0], dive.position[1]))
    assert off < 0.3, f"the hold should keep the vehicle near its station in a 0.3 m/s current, off by {off:.2f} m"
    # And it costs thrust: the horizontals are working against the water.
    assert float(np.mean(np.abs(dive.commands[:4]))) > 0.01


def test_still_water_is_the_default():
    model = Hydrodynamics.from_package(PACKAGE)
    dive = Dive({"durationSeconds": 10, "initialState": {"positionM": [0, 0, -7]}},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)
    assert np.allclose(dive.current, 0.0)
