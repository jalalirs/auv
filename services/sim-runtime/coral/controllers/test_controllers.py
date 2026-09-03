"""What the controllers must get right for a dive to begin still.

Run against the real integrator — the same Dive.step the simulator steps —
with nothing drawn and no Isaac Sim, because the trajectory does not depend on
either. A vehicle that holds station here holds it there.

Run with plain pytest from services/sim-runtime/coral.
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = HERE.parents[3] / "catalog/vehicles/bluerov2/dynamics.json"


def a_dive(start=(0.0, 0.0, -7.0), seconds: float = 60.0) -> Dive:
    model = Hydrodynamics.from_package(PACKAGE)
    body, allocator = Body(model), Allocator(model)
    brief = {"durationSeconds": seconds, "initialState": {"positionM": list(start)}}
    said = []
    dive = Dive(brief, body, allocator, pathlib.Path("nowhere.usda"), lambda kind, **d: said.append((kind, d)))
    dive.said = said
    return dive


def run(dive: Dive, seconds: float, each=None) -> None:
    steps = int(seconds / dive.dt)
    for k in range(steps):
        if each is not None:
            each(k * dive.dt)
        dive.step()


def test_a_dive_begins_under_the_hold_and_stays_put():
    dive = a_dive()
    run(dive, 60.0)
    assert dive.helm.flying.name == "hold"
    # The catalogue vehicle sinks by 1.7 N at rest; under the hold it does not.
    assert abs(-dive.position[2] - 7.0) < 0.03, f"depth drifted to {-dive.position[2]:.3f} m"
    assert np.hypot(dive.position[0], dive.position[1]) < 0.03
    assert abs(math.degrees(dive.observation().heading)) < 1.0


def test_the_hold_recovers_from_a_push():
    dive = a_dive()
    run(dive, 5.0)
    # A shove: a metre off station and half a metre deeper, at once.
    dive.position += np.array([1.0, 0.0, -0.5])
    run(dive, 40.0)
    assert np.hypot(dive.position[0], dive.position[1]) < 0.05
    assert abs(-dive.position[2] - 7.0) < 0.05


def test_hands_take_the_vehicle_and_the_hold_takes_it_back():
    dive = a_dive()
    run(dive, 3.0)
    assert dive.helm.flying.name == "hold"

    # Half ahead for ten seconds.
    dive.take_the_controls([0.5, 0.0, 0.0, 0.0, 0.0, 0.0])
    run(dive, 10.0)
    assert dive.helm.flying.name == "manual"
    assert dive.position[0] > 1.0, "half ahead for ten seconds should have moved it"
    # Assisted: depth held while pushing ahead.
    assert abs(-dive.position[2] - 7.0) < 0.15

    # Let go. The hold takes it where it is and keeps it there.
    dive.take_the_controls([0.0] * 6)
    where = dive.position.copy()
    run(dive, 30.0)
    assert dive.helm.flying.name == "hold"
    assert np.hypot(*(dive.position[:2] - where[:2])) < 0.4, "the hold should catch it near where it was left"
    assert abs(-dive.position[2] - 7.0) < 0.05


def test_a_turn_is_held_as_a_heading():
    dive = a_dive()
    run(dive, 3.0)
    dive.take_the_controls([0.0, 0.0, 0.0, 0.0, 0.0, 0.5])
    run(dive, 4.0)
    turned = dive.observation().heading
    assert abs(turned) > math.radians(15)
    dive.take_the_controls([0.0] * 6)
    run(dive, 20.0)
    assert abs(dive.observation().heading - turned) < math.radians(8)


def test_parameters_are_tunable_and_bounded():
    dive = a_dive()
    assert dive.helm.tune("hold", "depthKp", 3.0)
    assert dive.helm.hold["depthKp"] == 3.0
    dive.helm.tune("hold", "depthKp", 99.0)
    assert dive.helm.hold["depthKp"] == 4.0, "clamped to its range"
    assert not dive.helm.tune("hold", "nonsense", 1.0)
    told = dive.instruments()["controller"]
    assert told["flying"] == "hold"
    names = {c["name"] for c in told["controllers"]}
    assert {"hold", "manual"} <= names
    assert any(p["name"] == "depthKp" for c in told["controllers"] for p in c["parameters"])


def test_hold_here_moves_the_station():
    dive = a_dive()
    run(dive, 2.0)
    dive.take_the_controls([0.0, 0.0, -0.6, 0.0, 0.0, 0.0])
    run(dive, 6.0)
    dive.take_the_controls([0.0] * 6)
    dive.message({"hold": "here"})
    deeper = dive.helm.hold.target_depth
    assert deeper > 7.3
    run(dive, 20.0)
    assert abs(-dive.position[2] - deeper) < 0.05


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_a_roll_key_leans_the_hull_and_lets_it_come_back():
    dive = a_dive()
    run(dive, 3.0)
    dive.take_the_controls([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    run(dive, 8.0)
    rolled = math.degrees(dive.observation().roll)
    assert 5.0 < abs(rolled) < 35.0, f"a full roll key should lean the hull, not capsize it: {rolled:.1f}°"
    dive.take_the_controls([0.0] * 6)
    run(dive, 15.0)
    assert abs(math.degrees(dive.observation().roll)) < 3.0, "let go, it rights itself"
