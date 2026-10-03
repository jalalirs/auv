"""Propellers that turn at the speed their command gives them.

The speed is worked out on simulated time by the thrusters' system and drawn
by draw/propellers.py; neither touches the physics, so these check the
arithmetic and the shape, not a picture.
"""

import math

import numpy as np

from draw import propellers
from systems.thrusters import Thrust


def test_full_command_is_full_speed_and_reverse_turns_the_other_way():
    t = Thrust(3)
    t.commands = np.array([1.0, -1.0, 0.0])
    t.turn(0.005)
    assert t.rpm[0] == t.max_rpm[0]
    assert t.rpm[1] == -t.max_rpm[1]
    assert t.rpm[2] == 0.0


def test_a_quarter_of_the_thrust_is_half_the_speed():
    """Thrust goes as the square of a propeller's speed."""
    t = Thrust(1)
    t.commands = np.array([0.25])
    t.turn(0.005)
    assert math.isclose(t.rpm[0], 0.5 * t.max_rpm[0])


def test_the_angle_is_kept_in_simulated_time():
    """A second at sixty revolutions a second is sixty whole turns: back where
    it started, however the dive was drawn."""
    t = Thrust(1)
    t.max_rpm = np.array([3600.0])
    t.commands = np.array([1.0])
    for _ in range(200):
        t.turn(0.005)
    assert min(t.angle[0], 2 * math.pi - t.angle[0]) < 1e-6


def test_a_package_that_states_nothing_is_assumed_and_says_so(tmp_path):
    t = Thrust(2)
    (tmp_path / "dynamics.json").write_text('{"thrusters": {}}')
    t.read_the_package(tmp_path / "dynamics.json")
    assert t.diameter_m is None
    assert t.rpm_from.startswith("assumed")


def test_a_package_that_states_its_propellers_is_believed(tmp_path):
    t = Thrust(2)
    (tmp_path / "dynamics.json").write_text(
        '{"thrusters": {"maxRpm": 3000, "rpmFrom": "datasheet", "propellerDiameterM": 0.07}}')
    t.read_the_package(tmp_path / "dynamics.json")
    assert list(t.max_rpm) == [3000.0, 3000.0]
    assert t.diameter_m == 0.07 and t.rpm_from == "datasheet"


def test_the_blades_are_as_wide_as_the_propeller():
    points, faces = propellers.blade_mesh(0.019)
    reach = np.hypot(points[:, 0], points[:, 1]).max()
    assert math.isclose(reach, 0.019, rel_tol=1e-6)
    assert faces.max() < len(points)


def test_a_propeller_faces_the_way_its_thruster_pushes():
    for way in ([0, 0, 1], [0.707, 0.707, 0], [-0.707, -0.707, 0], [0, 0, -1]):
        w, x, y, z = propellers.facing(way)
        # Rotate +z by the quaternion.
        q = np.array([x, y, z])
        v = np.array([0.0, 0.0, 1.0])
        turned = v + 2 * w * np.cross(q, v) + 2 * np.cross(q, np.cross(q, v))
        assert np.allclose(turned, np.asarray(way) / np.linalg.norm(way), atol=1e-6)


def test_the_blur_is_nothing_standing_still_and_never_solid():
    assert propellers.blur(0.0, 3600.0) == 0.0
    assert 0.0 < propellers.blur(900.0, 3600.0) < propellers.blur(3600.0, 3600.0) <= 0.6


def test_blades_turning_faster_than_a_frame_can_follow_are_not_drawn():
    """A three-bladed propeller turning 3,600 rpm moves 900 degrees between
    frames at 24 a second: drawn, its blades land somewhere new each frame and
    flash. Standing still or creeping they are drawn; turning, the blur is."""
    assert propellers.blades_seen(0.0) == 1.0
    assert propellers.blades_seen(30.0) == 1.0             # 7.5 degrees a frame
    assert propellers.blades_seen(3600.0) == 0.0
    assert 0.0 < propellers.blades_seen(100.0) < 1.0       # 25 degrees a frame: fading
    # A faster film resolves faster blades.
    assert propellers.blades_seen(100.0, frame_s=1 / 120) == 1.0


def test_where_the_blades_go_the_blur_comes_in():
    assert propellers.disc_seen(0.0, 3600.0) == 0.0
    turning = propellers.disc_seen(200.0, 3600.0)
    assert propellers.blades_seen(200.0) == 0.0 and turning > 0.15, turning
    assert propellers.disc_seen(3600.0, 3600.0) <= propellers.MOST_BLUR + 1e-9
