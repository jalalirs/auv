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


# ── ground ahead, not only ground below ──────────────────────────────────────

def a_seabed(build):
    """A 64 by 64 bottom over a hundred metres, from a function of x and y."""
    from runner import Seabed

    across, cells = 100.0, 64
    heights = np.zeros((cells, cells))
    for row in range(cells):
        for column in range(cells):
            x = (column / (cells - 1) - 0.5) * across
            y = (row / (cells - 1) - 0.5) * across
            heights[row, column] = build(x, y)
    return Seabed(heights, across)


def test_the_bottom_says_which_way_it_faces():
    flat = a_seabed(lambda x, y: -10.0)
    assert np.allclose(flat.normal(0.0, 0.0), [0, 0, 1], atol=1e-6), "flat ground faces up"
    # A ramp climbing towards +x: the normal leans back against the climb.
    ramp = a_seabed(lambda x, y: -10.0 + x)
    faces = ramp.normal(0.0, 0.0)
    assert faces[0] < -0.6 and faces[2] > 0.6, f"a one-in-one ramp faces up and back, got {faces}"


def test_a_wall_stops_the_vehicle_and_a_slope_does_not():
    # A face rising steeply beyond x = 0, ten metres tall.
    wall = a_seabed(lambda x, y: -10.0 + (0.0 if x < 0 else min(10.0, x * 8.0)))
    dive = a_dive(depth=9.0)
    dive.seabed = wall
    dive.half_width, dive.half_height = 0.3, 0.13
    dive.position = np.array([-0.4, 0.0, -9.0])
    dive.velocity[:3] = np.array([0.5, 0.0, 0.0])          # driving at the face
    dive.strike()
    assert dive.against_the_ground, "it should be stopped by ground it cannot climb"
    assert abs(float(dive.velocity[0])) < 1e-6, "the motion into the wall is taken away"

    # The same vehicle on a one-in-ten slope keeps going.
    slope = a_seabed(lambda x, y: -10.0 + x * 0.1)
    dive.seabed = slope
    dive.against_the_ground = False
    dive.velocity[:3] = np.array([0.5, 0.0, 0.0])
    dive.strike()
    assert not dive.against_the_ground, "a gentle slope is ground, not a wall"
    assert abs(float(dive.velocity[0]) - 0.5) < 1e-9


def test_a_vehicle_stopped_by_a_wall_still_slides_along_it():
    wall = a_seabed(lambda x, y: -10.0 + (0.0 if x < 0 else min(10.0, x * 8.0)))
    dive = a_dive(depth=9.0)
    dive.seabed = wall
    dive.half_width, dive.half_height = 0.3, 0.13
    dive.position = np.array([-0.4, 0.0, -9.0])
    dive.velocity[:3] = np.array([0.5, 0.4, 0.0])          # into the wall and along it
    dive.strike()
    assert abs(float(dive.velocity[0])) < 1e-6, "nothing goes into the face"
    assert abs(float(dive.velocity[1]) - 0.4) < 1e-9, "what runs along it is untouched"


def test_ground_below_the_keel_is_not_a_wall():
    wall = a_seabed(lambda x, y: -10.0 + (0.0 if x < 0 else min(10.0, x * 8.0)))
    dive = a_dive(depth=1.0)
    dive.seabed = wall
    dive.half_width, dive.half_height = 0.3, 0.13
    dive.position = np.array([-0.4, 0.0, -1.0])            # flying well over the spur
    dive.velocity[:3] = np.array([0.5, 0.0, 0.0])
    dive.strike()
    assert not dive.against_the_ground, "a wall it is flying over is not in its way"
    assert abs(float(dive.velocity[0]) - 0.5) < 1e-9


def test_a_vehicle_driven_at_a_spur_does_not_climb_it():
    wall = a_seabed(lambda x, y: -10.0 + (0.0 if x < 0 else min(10.0, x * 8.0)))
    dive = a_dive(depth=9.0, seconds=40)
    dive.seabed = wall
    dive.half_width, dive.half_height = 0.3, 0.13
    dive.position = np.array([-3.0, 0.0, -9.5])
    ahead = np.zeros(6)
    ahead[0] = dive.helm.capability[0]
    for _ in range(int(20.0 / dive.dt)):
        dive.commands = dive.allocator.allocate(ahead)
        wrench = dive.body.step(dive.rotation, dive.velocity, dive.commands, dive.dt, 1.0)
        dive.velocity[:3] += (wrench[:3] / dive.effective[:3]) * dive.dt
        dive.velocity[3:] += (wrench[3:] / dive.effective[3:]) * dive.dt
        dive.position += dive.rotation @ dive.velocity[:3] * dive.dt
        dive.rotation = dive.rotation
        dive.land()
    assert dive.position[0] < 0.2, f"it drove into the face and up it, reaching x = {dive.position[0]:.2f} m"
    assert dive.against_the_ground, "it should end the run held against the face"
    under = wall.under(float(dive.position[0]), float(dive.position[1]))
    assert under <= dive.position[2] - dive.half_height + 1e-6, "and never inside the ground"
    # It does rise, because full surge on a frame whose thrusters sit above its
    # centre of gravity pitches the hull and turns some of that push upwards.
    # That is the hull, not the terrain, and the guard has nothing to say about it.


def test_a_slope_is_climbed_at_a_cost_rather_than_for_free():
    """A vehicle pressed onto a slope goes along it, not through it — and pays.

    The old floor clamped depth and nothing else, so a vehicle driven at a
    rise was carried up it with its speed intact. What the ground can do is
    turn motion, not add it.
    """
    slope = a_seabed(lambda x, y: -10.0 + x * 0.7)      # thirty-five degrees
    dive = a_dive(depth=9.0)
    dive.seabed = slope
    dive.half_width, dive.half_height = 0.3, 0.13
    here = slope.under(0.0, 0.0)
    dive.position = np.array([0.0, 0.0, here + dive.half_height - 0.02])   # pressed in
    dive.velocity[:3] = np.array([0.6, 0.0, 0.0])
    before = float(np.linalg.norm(dive.velocity[:3]))
    dive.land()

    assert dive.position[2] >= here + dive.half_height - 1e-9, "it is put back on the surface"
    after = dive.velocity[:3].copy()
    assert after[0] < 0.6, "the push into the slope is spent"
    assert after[2] > 0.0, "and some of it becomes travel up the slope"
    assert float(np.linalg.norm(after)) <= before + 1e-9, "the ground never adds speed"
    assert dive.on_the_bottom, "thirty-five degrees is ground to rest on"


def test_a_flat_bottom_still_simply_stops_it():
    flat = a_seabed(lambda x, y: -10.0)
    dive = a_dive(depth=9.0)
    dive.seabed = flat
    dive.half_width, dive.half_height = 0.3, 0.13
    dive.position = np.array([0.0, 0.0, -10.0])
    dive.velocity[:3] = np.array([0.3, 0.0, -0.4])
    dive.land()
    assert abs(float(dive.velocity[2])) < 1e-9, "the descent is taken away"
    assert abs(float(dive.velocity[0]) - 0.3) < 1e-9, "what runs along the bottom is not"
    assert dive.on_the_bottom
