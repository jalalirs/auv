"""Where the vehicle thinks it is: drift, fixes, and what it costs a task.

A dive flown on the simulator's own truth is not a dive. These are the tests
that the vehicle is working from its instruments — and that the instruments
are wrong in the ways real ones are.
"""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from navigation import Navigation  # noqa: E402
from runner import Dive  # noqa: E402

VEHICLE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"


def a_dive(objective=None, positioning=None, fitted=None, seconds=600, seed=7):
    model = Hydrodynamics.from_package(VEHICLE / "dynamics.json")
    parameters = {}
    if positioning is not None:
        parameters["positioning"] = positioning
    if fitted is not None:
        parameters["fitted"] = fitted
    brief = {"durationSeconds": seconds, "seed": seed, "vehiclePath": str(VEHICLE),
             "initialState": {"positionM": [0, 0, -6]},
             "conditions": {"kind": "constructed", "parameters": parameters}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **said: None)
    dive.floor = -12.0
    if objective is not None:
        dive.begin_task(objective)
    else:
        dive.begin_task({"kind": "hold-station", "seconds": 5})
    return dive


def swim(dive, seconds, speed=0.4):
    """Fly it along at a steady speed without asking the controllers."""
    for _ in range(int(seconds / dive.dt)):
        dive.velocity[:3] = np.array([speed, 0.0, 0.0])
        floor = dive.floor
        dive.navigation.step(dive.simulated, dive.position, dive.velocity, dive.rotation, floor, dive.dt)
        dive.position += dive.rotation @ dive.velocity[:3] * dive.dt
        dive.simulated += dive.dt


# ── what the vehicle is handed ───────────────────────────────────────────────

def test_a_controller_is_handed_the_estimate_and_never_the_truth():
    dive = a_dive()
    swim(dive, 120.0)
    seen = dive.observation()
    assert not np.allclose(seen.position[:2], dive.position[:2]), (
        "the controller must be working from the estimate, not the simulator's truth")
    assert np.allclose(seen.position[:2], dive.navigation.believed[:2])
    # Depth is not dead reckoned: pressure is depth, and it does not drift.
    assert abs(seen.depth - float(-dive.position[2])) < 0.1


def test_the_compass_is_what_it_is_wrong_by():
    dive = a_dive()
    believed = dive.navigation.believed_rotation(dive.rotation)
    said = math.atan2(float(believed[1, 0]), float(believed[0, 0]))
    truth = math.atan2(float(dive.rotation[1, 0]), float(dive.rotation[0, 0]))
    assert abs(said - truth) > 1e-6, "a magnetometer in a steel frame is not perfect"
    assert abs(said - truth) < math.radians(10.0), "nor is it hopeless"


# ── dead reckoning ───────────────────────────────────────────────────────────

def test_dead_reckoning_drifts_with_the_distance_travelled():
    dive = a_dive()
    swim(dive, 60.0)
    near = dive.navigation.drift(dive.position)
    swim(dive, 240.0)
    far = dive.navigation.drift(dive.position)
    assert far > near, "error grows with the ground covered, not with the clock"
    travelled = dive.navigation.travelled
    assert 0.001 * travelled < far < 0.15 * travelled, (
        f"drifted {far:.1f} m over {travelled:.0f} m, which is not a real vehicle")


def test_without_a_doppler_log_it_is_much_worse():
    with_log = a_dive(seed=3)
    swim(with_log, 200.0)
    without = a_dive(fitted={"dvl": False}, seed=3)
    swim(without, 200.0)
    assert without.navigation.drift(without.position) > with_log.navigation.drift(with_log.position) * 2, (
        "a vehicle with no bottom lock is guessing at its speed")
    assert not without.navigation.bottom_lock


def test_the_log_loses_the_bottom_when_the_bottom_is_out_of_range():
    dive = a_dive()
    dive.floor = -12.0
    dive.position[2] = -6.0
    dive.navigation.step(0.0, dive.position, dive.velocity, dive.rotation, dive.floor, dive.dt)
    assert dive.navigation.bottom_lock, "six metres up is well within an A50's range"
    dive.floor = -400.0
    dive.navigation.step(0.1, dive.position, dive.velocity, dive.rotation, dive.floor, dive.dt)
    assert not dive.navigation.bottom_lock, "four hundred metres of water under it is not"


# ── fixes ────────────────────────────────────────────────────────────────────

def test_a_usbl_from_the_surface_pulls_it_back():
    drifting = a_dive(seed=11)
    swim(drifting, 300.0)
    aided = a_dive(positioning={"kind": "usbl", "everyS": 2.0, "accuracyPercent": 0.5,
                                "at": [0.0, 0.0, 0.0]}, seed=11)
    swim(aided, 300.0)
    assert aided.navigation.fixes > 50, "it should have been fixed all the way"
    assert aided.navigation.drift(aided.position) < drifting.navigation.drift(drifting.position), (
        "a fix from outside is the only thing that stops the drift growing")
    assert "USBL" in aided.navigation.last_fix_from


def test_an_lbl_array_only_works_inside_itself():
    dive = a_dive(positioning={"kind": "lbl", "everyS": 2.0, "accuracyM": 0.5,
                               "at": [0.0, 0.0, -10.0], "rangeM": 60.0}, seed=5)
    swim(dive, 100.0)              # forty metres out: inside the array
    assert dive.navigation.fixes > 10, "inside the array it is fixed every few seconds"
    swim(dive, 200.0)              # out through the edge of it
    left = dive.navigation.fixes
    swim(dive, 200.0)              # and well beyond
    assert dive.navigation.fixes == left, "ranging to transponders it cannot hear is not a degraded fix"
    assert dive.navigation.drift(dive.position) > 0.2, "and the drift comes back with it"


def test_the_surface_is_a_fix():
    dive = a_dive(seed=2)
    swim(dive, 200.0)
    drifted = dive.navigation.drift(dive.position)
    assert drifted > 0.2
    dive.position[2] = -0.2                 # up it comes
    dive.navigation.step(dive.simulated, dive.position, np.zeros(6), dive.rotation, dive.floor, dive.dt)
    assert dive.navigation.drift(dive.position) < max(6.0, drifted), "the sky is where the fix is"
    assert "satellite" in dive.navigation.last_fix_from


# ── what it costs ────────────────────────────────────────────────────────────

def test_two_runs_of_one_seed_drift_the_same_way():
    first, second = a_dive(seed=9), a_dive(seed=9)
    swim(first, 180.0)
    swim(second, 180.0)
    assert np.allclose(first.navigation.believed, second.navigation.believed, atol=1e-12), (
        "a navigation error that changed between runs would make every comparison meaningless")


def test_navigation_error_is_what_makes_a_far_point_hard():
    """Flown on its own instruments, the vehicle arrives where it believes the
    point is — and the task scores where it actually is."""
    dive = a_dive(objective={"kind": "reach", "dx": 120.0, "dy": 0.0, "radiusM": 2.0,
                             "timeLimitS": 900.0}, seconds=1200, seed=4)
    for _ in range(int(900 / dive.dt)):
        dive.step()
        if dive.done:
            break
    believed = dive.navigation.believed
    target = dive.task.target
    assert float(np.linalg.norm(believed[:2] - target[:2])) < 4.0, (
        "it should believe it got there")
    off = float(np.linalg.norm(dive.position[:2] - target[:2]))
    assert off > 0.05, f"and be somewhere else, but it was {off:.2f} m off"
    assert dive.navigation.drift(dive.position) > 0.05
