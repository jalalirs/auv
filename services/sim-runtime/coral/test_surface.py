"""The two edges of the water: the top of it and the bottom of it.

A vehicle that rises through the surface has to lose the water — its
buoyancy, its drag, the bite of its thrusters and the water that accelerates
with it — or it flies. A vehicle driven at the seabed has to be held off it,
because nothing else in the vehicle knows the ground is there.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from controllers import Observation  # noqa: E402
from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"


def a_dive(depth=4.0, seconds=60):
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": seconds, "initialState": {"positionM": [0, 0, -depth]}}
    return Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)


def test_the_hull_goes_under_over_its_own_height():
    dive = a_dive()
    dive.half_height = 0.13
    dive.position[2] = -1.0
    assert dive.submerged() == 1.0, "a metre down is under the water"
    dive.position[2] = 0.0
    assert 0.4 < dive.submerged() < 0.6, "at the waterline it is about half in"
    dive.position[2] = 0.5
    assert dive.submerged() == 0.0, "clear of the water it is out of it"


def test_a_vehicle_driven_up_hard_breaks_the_surface_and_falls_back():
    dive = a_dive(depth=1.0, seconds=40)
    # Full ascent, held on, which is what a pilot leaning on the up key does.
    up = np.zeros(6)
    up[2] = dive.helm.capability[2]
    for _ in range(int(12.0 / dive.dt)):
        dive.commands = dive.allocator.allocate(up)
        through_water = dive.velocity.copy()
        wrench = dive.body.step(dive.rotation, through_water, dive.commands, dive.dt, dive.submerged())
        effective = dive.body.effective_mass(dive.submerged())
        dive.velocity[:3] += (wrench[:3] / effective[:3]) * dive.dt
        dive.velocity[3:] += (wrench[3:] / effective[3:]) * dive.dt
        dive.position += dive.rotation @ dive.velocity[:3] * dive.dt
        dive.simulated += dive.dt
        dive.land()

    assert dive.position[2] < 0.6, (
        f"a thruster in air cannot push it out of the sea; it reached {dive.position[2]:.2f} m above the water")
    assert dive.submerged() > 0.0, "it should settle back into the water, not sit on top of it"


def test_out_of_the_water_it_weighs_what_it_weighs():
    model = Hydrodynamics.from_package(PACKAGE)
    body = Body(model)
    level = np.eye(3)
    under, _ = body.restoring(level, 1.0)
    out, _ = body.restoring(level, 0.0)
    assert abs(under[2] - model.net_buoyancy_n) < 1e-6, "under water it is nearly neutral"
    assert abs(out[2] + model.weight_n) < 1e-6, "out of it there is nothing holding it up"
    assert np.allclose(body.thrust(np.ones(len(model.thrusters)), 0.0), 0.0), "propellers need water"
    assert np.allclose(body.damping(np.ones(6), 0.0), 0.0), "and so does drag"


def test_the_guard_holds_the_vehicle_off_the_seabed():
    dive = a_dive(depth=4.0)
    floor = -5.0
    down = np.zeros(6)
    down[2] = -dive.helm.capability[2]

    def seen(z):
        return Observation(t=0.0, position=np.array([0.0, 0.0, z]), velocity=np.zeros(6),
                           rotation=np.eye(3), floor=floor, on_the_bottom=False)

    clear = dive.helm.bottom(down.copy(), seen(floor + 3.0))
    assert clear[2] == down[2], "with water under it, full descent is allowed"
    close = dive.helm.bottom(down.copy(), seen(floor + 0.25))
    assert -down[2] / 2.5 < -close[2] < -down[2], "half a metre up, half the descent"
    at_it = dive.helm.bottom(down.copy(), seen(floor + 0.001))
    assert abs(at_it[2]) < 0.01 * dive.helm.capability[2], "at the bottom, next to none of it"
    rising = np.zeros(6)
    rising[2] = dive.helm.capability[2]
    assert dive.helm.bottom(rising.copy(), seen(floor + 0.001))[2] == rising[2], "it may always go up"


def test_the_guard_can_be_turned_off():
    dive = a_dive()
    dive.helm.tune("helm", "bottomGuardM", 0.0)
    down = np.zeros(6)
    down[2] = -dive.helm.capability[2]
    held = dive.helm.bottom(down.copy(), Observation(
        t=0.0, position=np.array([0.0, 0.0, -4.99]), velocity=np.zeros(6),
        rotation=np.eye(3), floor=-5.0, on_the_bottom=False))
    assert held[2] == down[2], "a guard set to zero is a guard that is off"


def test_a_dive_flown_by_the_hold_keeps_its_clearance():
    dive = a_dive(depth=4.0, seconds=30)
    dive.floor = -4.2                       # the hold's station is 20 cm off the bottom
    for _ in range(int(20.0 / dive.dt)):
        dive.step()
    assert dive.position[2] > -4.2, "it must not end up under the seabed"
    assert dive.helm.altitude is not None and dive.helm.altitude >= 0.0
