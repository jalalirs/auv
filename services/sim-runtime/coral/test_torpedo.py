"""The REMUS 100: a propeller on the axis, and fins that only work while it moves.

It cannot push sideways or straight up, so it turns on its rudder and dives
on its stern planes, and stopped it cannot steer at all. The coefficients are
Prestero's (2001); what is checked here is that they act where and when they
should, and that a route flown on them arrives.
"""

import math
import pathlib
import sys
import warnings

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/remus-100/dynamics.json"


def a_torpedo():
    return Hydrodynamics.from_package(PACKAGE)


def test_fins_do_nothing_at_rest():
    model = a_torpedo()
    model.fin_rad[:] = [0.2, 0.2]
    assert np.allclose(Body(model).steering(np.zeros(6)), 0.0)


def test_rudder_turns_it_to_port_and_planes_lift_the_nose():
    model = a_torpedo()
    body = Body(model)
    going = np.array([1.5, 0, 0, 0, 0, 0.0])
    model.fin_rad[:] = [0.2, 0.0]
    yaw = body.steering(going)[5]
    assert yaw > 0.0, "a positive rudder turns the nose to port"
    # Prestero's N_uudr is the fin lift times its arm: 6.15 kg/rad.
    assert math.isclose(yaw, 6.15 * 1.5 ** 2 * 0.2, rel_tol=0.02)
    model.fin_rad[:] = [0.0, 0.2]
    # Nose-down is positive pitch in this z-up frame, so lifting the nose is negative.
    assert body.steering(going)[4] < 0.0


def test_it_cannot_hover():
    assert not a_torpedo().can_hover


def a_dive_of(objective, seconds=900.0, positioning=None):
    from runner import Dive
    said = []
    model = a_torpedo()
    parameters = {} if positioning is None else {"positioning": positioning}
    brief = {"durationSeconds": seconds,
             "initialState": {"positionM": [0, 0, -10]},
             "conditions": {"kind": "constructed", "parameters": parameters},
             "objective": objective}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **detail: said.append((kind, detail)))
    return dive, said


def test_asked_to_hold_station_it_says_it_cannot_and_what_it_can():
    dive, said = a_dive_of({"kind": "hold-station", "seconds": 300})
    dive.begin_task(dive.brief["objective"])
    refusals = [d for k, d in said if k == "task_refused"]
    assert refusals and "waypoints" in refusals[0]["instead"]
    assert dive.task is None


def test_a_mission_of_routes_is_accepted_and_one_with_a_hold_is_not():
    moving = {"kind": "mission", "stages": [{"kind": "waypoints", "points": [{"x": 50, "y": 0}]},
                                            {"kind": "transect", "from": {"x": 50, "y": 0}, "to": {"x": 50, "y": 60}}]}
    dive, said = a_dive_of(moving)
    dive.begin_task(moving)
    assert dive.task is not None and not [d for k, d in said if k == "task_refused"]
    stopping = {"kind": "mission", "stages": [{"kind": "waypoints", "points": [{"x": 50, "y": 0}]},
                                              {"kind": "hold-station", "seconds": 60}]}
    dive, said = a_dive_of(stopping)
    dive.begin_task(stopping)
    assert dive.task is None


def test_it_flies_a_route_round_a_corner_on_its_fins():
    """Three points with turns between them, with a position fix so that what
    is tested is the steering and not the dead reckoning."""
    objective = {"kind": "mission", "stages": [{"kind": "waypoints", "radiusM": 8, "timeLimitS": 600,
                 "points": [{"x": 100, "y": 0, "depthM": 10}, {"x": 100, "y": 100, "depthM": 15},
                            {"x": 0, "y": 100, "depthM": 10}]}]}
    dive, _ = a_dive_of(objective, seconds=600,
                        positioning={"kind": "usbl", "accuracyM": 1.0, "everyS": 2.0})
    dive.begin_task(objective)
    assert dive.helm.flying.name == "fins"
    for _ in range(int(600 / dive.dt)):
        dive.step()
        if dive.done:
            break
    done = dive.task.result()["achieved"]["stages"][0]
    assert done["achieved"]["reached"] == 3, done
