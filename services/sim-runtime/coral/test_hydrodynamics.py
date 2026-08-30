"""What the model must get right for a dive to mean anything.

These check physics rather than plumbing: that a vehicle rights itself, that
drag opposes motion, that thrust allocation produces the wrench it was asked
for. A model that fails any of these produces results that look real and are
not, which is the failure mode worth spending tests on.

Run with plain pytest; nothing here needs Isaac Sim.
"""

import json
import math
import pathlib

import numpy as np
import pytest

from hydrodynamics import (
    GRAVITY,
    Allocator,
    Body,
    Hydrodynamics,
    Thruster,
    terminal_velocity,
)

PACKAGE = pathlib.Path(__file__).parents[3] / "catalog/vehicles/bluerov2/dynamics.json"


def bluerov() -> Hydrodynamics:
    return Hydrodynamics.from_package(PACKAGE)


def identity() -> np.ndarray:
    return np.eye(3)


def rotation_about_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


# ── what the vehicle is ──────────────────────────────────────────────────────

def test_the_published_vehicle_loads():
    model = bluerov()
    assert model.mass_kg == pytest.approx(11.5)
    assert len(model.thrusters) == 6


def test_it_is_very_nearly_neutrally_buoyant():
    # A survey ROV is ballasted so that it neither sinks like a stone nor
    # fights its own buoyancy to stay down. Weight and buoyancy should be
    # within a few per cent, and a model where they are not is a model of a
    # different vehicle.
    model = bluerov()
    assert model.buoyancy_n == pytest.approx(model.weight_n, rel=0.05)


def test_centres_that_coincide_are_refused():
    # Not fussiness: the distance between them is the lever arm that rights the
    # vehicle. Let them coincide and it holds any attitude it is pushed into,
    # and does so without any error at all.
    with pytest.raises(ValueError, match="restoring moment"):
        Hydrodynamics(
            mass_kg=11.5, displaced_volume_m3=0.011,
            centre_of_gravity=np.zeros(3), centre_of_buoyancy=np.zeros(3),
            added_mass=np.ones(6), linear_damping=np.ones(6), quadratic_damping=np.ones(6),
        )


# ── restoring ────────────────────────────────────────────────────────────────

def test_upright_and_level_it_neither_rolls_nor_pitches():
    body = Body(bluerov())
    _, moment = body.restoring(identity())
    assert moment[0] == pytest.approx(0.0, abs=1e-9)
    assert moment[1] == pytest.approx(0.0, abs=1e-9)


def test_rolled_over_it_rights_itself():
    # The test that matters. Roll the vehicle and the moment must act to undo
    # the roll, at every angle short of exactly upside down.
    body = Body(bluerov())
    for degrees in (5, 15, 30, 60, 90, 135, 175):
        rotation = rotation_about_x(math.radians(degrees))
        _, moment = body.restoring(rotation)
        assert moment[0] < 0, (
            f"rolled {degrees}° the vehicle is pushed further over, not back")


def test_exactly_inverted_it_is_balanced_and_will_not_recover_alone():
    # Upside down the two centres are again in line, so there is no righting
    # moment at all. That is true of the real vehicle, and a model that quietly
    # rights it from inverted would be lying about a situation an operator
    # genuinely has to get out of with thrust.
    body = Body(bluerov())
    _, moment = body.restoring(rotation_about_x(math.pi))
    assert abs(moment[0]) < 1e-9


def test_the_righting_moment_is_strongest_on_its_side():
    body = Body(bluerov())
    at = {d: abs(body.restoring(rotation_about_x(math.radians(d)))[1][0])
          for d in (30, 90, 150)}
    assert at[90] > at[30]
    assert at[90] > at[150]


# ── drag ─────────────────────────────────────────────────────────────────────

def test_drag_always_opposes_motion():
    body = Body(bluerov())
    for axis in range(6):
        for speed in (0.05, 0.5, 2.0):
            velocity = np.zeros(6)
            velocity[axis] = speed
            assert body.damping(velocity)[axis] < 0
            velocity[axis] = -speed
            assert body.damping(velocity)[axis] > 0


def test_drag_grows_faster_than_speed():
    # Because the quadratic term takes over. A controller tuned only at low
    # speed will undershoot at high speed, and that is a property of water
    # rather than of this implementation.
    body = Body(bluerov())
    slow, fast = np.zeros(6), np.zeros(6)
    slow[0], fast[0] = 0.1, 1.0
    assert abs(body.damping(fast)[0]) > 10 * abs(body.damping(slow)[0])


def test_heave_is_the_draggiest_axis():
    # The frame presents its widest face to vertical motion. A controller that
    # does not know this overshoots every depth change.
    model = bluerov()
    assert model.quadratic_damping[2] > model.quadratic_damping[0]
    assert model.quadratic_damping[2] > model.quadratic_damping[1]


def test_at_rest_the_water_does_nothing():
    body = Body(bluerov())
    assert np.allclose(body.damping(np.zeros(6)), np.zeros(6))


# ── added mass ───────────────────────────────────────────────────────────────

def test_added_mass_opposes_acceleration_and_not_velocity():
    body = Body(bluerov())
    steady = np.array([1.0, 0, 0, 0, 0, 0])

    body.added_mass(steady, 0.01)                    # first step only records
    assert np.allclose(body.added_mass(steady, 0.01), np.zeros(6)), (
        "moving at a constant speed, added mass should produce nothing")

    accelerating = np.array([2.0, 0, 0, 0, 0, 0])
    assert body.added_mass(accelerating, 0.01)[0] < 0, (
        "accelerating forward, added mass should push back")


def test_added_mass_is_not_negligible_for_this_hull():
    # Heave added mass is 14.6 kg against a hull of 11.5. A model that leaves it
    # out has the vehicle accelerating roughly twice as readily as the real one,
    # which is not a detail.
    model = bluerov()
    assert model.added_mass[2] > model.mass_kg


# ── thrust ───────────────────────────────────────────────────────────────────

def test_a_thruster_pushes_less_hard_backwards():
    # A T200 gives about 51 N forward and 40 N reverse. A controller assuming
    # symmetry trims to one side.
    model = bluerov()
    forward, _ = model.thrusters[0].wrench(1.0)
    reverse, _ = model.thrusters[0].wrench(-1.0)
    assert np.linalg.norm(forward) > np.linalg.norm(reverse)


def test_a_command_beyond_full_is_clamped_rather_than_believed():
    model = bluerov()
    full, _ = model.thrusters[0].wrench(1.0)
    more, _ = model.thrusters[0].wrench(4.0)
    assert np.allclose(full, more)


def test_the_vertical_thrusters_lift_and_the_horizontal_ones_do_not():
    model = bluerov()
    vertical = [t for t in model.thrusters if t.name.startswith("vertical")]
    horizontal = [t for t in model.thrusters if not t.name.startswith("vertical")]
    assert len(vertical) == 2 and len(horizontal) == 4
    for thruster in vertical:
        assert thruster.wrench(1.0)[0][2] > 0
    for thruster in horizontal:
        assert thruster.wrench(1.0)[0][2] == pytest.approx(0.0, abs=1e-9)


# ── allocation ───────────────────────────────────────────────────────────────

def test_asking_to_go_forward_produces_forward():
    allocator = Allocator(bluerov())
    wanted = np.array([20.0, 0, 0, 0, 0, 0])
    produced = allocator.matrix @ allocator.allocate(wanted)
    assert produced[0] == pytest.approx(20.0, rel=0.02)
    assert abs(produced[1]) < 1e-6
    assert abs(produced[5]) < 1e-6


def test_asking_to_yaw_produces_yaw_and_no_translation():
    allocator = Allocator(bluerov())
    wanted = np.array([0, 0, 0, 0, 0, 3.0])
    produced = allocator.matrix @ allocator.allocate(wanted)
    assert produced[5] == pytest.approx(3.0, rel=0.05)
    assert np.linalg.norm(produced[:3]) < 1e-6


def test_asking_for_more_than_the_vehicle_has_is_reported_as_such():
    allocator = Allocator(bluerov())
    assert allocator.achievable(np.array([20.0, 0, 0, 0, 0, 0]))
    assert not allocator.achievable(np.array([10_000.0, 0, 0, 0, 0, 0]))


def test_a_vehicle_with_no_thrusters_cannot_be_flown():
    model = bluerov()
    model.thrusters = []
    with pytest.raises(ValueError, match="no thrusters"):
        Allocator(model)


# ── whole-body behaviour ─────────────────────────────────────────────────────

def test_released_upright_and_still_it_barely_moves():
    # Nearly neutral means the net vertical force is small compared with what
    # one thruster produces. If this vehicle sank or rose hard, the ballasting
    # in the package would be wrong.
    body = Body(bluerov())
    wrench = body.step(identity(), np.zeros(6), np.zeros(6), 1 / 60)
    assert abs(wrench[2]) < 10.0


def test_it_settles_rather_than_accelerating_for_ever():
    # Drag must eventually balance the buoyancy imbalance. A model where it
    # does not has a sign error somewhere, and the symptom is a vehicle that
    # leaves the scene.
    speed = terminal_velocity(bluerov(), axis=2)
    assert 0.0 < speed < 5.0, f"terminal speed of {speed} m/s is not a submarine"


def test_a_steady_thrust_reaches_a_steady_speed():
    # Integrate crudely and check the speed stops rising. This is the property
    # a pilot notices first and the one a broken drag term destroys.
    model = bluerov()
    body = Body(model)
    velocity = np.zeros(6)
    commands = np.array([0.5, 0.5, -0.5, -0.5, 0.0, 0.0])   # forward
    dt = 1 / 200

    speeds = []
    for _ in range(4000):
        wrench = body.step(identity(), velocity, commands, dt)
        acceleration = wrench[:3] / model.mass_kg
        velocity[:3] += acceleration * dt
        speeds.append(velocity[0])

    assert speeds[-1] > 0.1, "steady forward thrust produced no forward motion"
    assert speeds[-1] < 5.0, "it never stopped accelerating"
    assert abs(speeds[-1] - speeds[-200]) < 0.02, "it had not settled"


def test_gravity_is_switched_on():
    # The thing OceanSim turns off. Weight must be a real force in the model,
    # not something cancelled by fiat, or buoyancy has nothing to act against
    # and the vehicle has no vertical dynamics at all.
    model = bluerov()
    assert model.weight_n == pytest.approx(11.5 * GRAVITY)
    assert model.weight_n > 100.0
