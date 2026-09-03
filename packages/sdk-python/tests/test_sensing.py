import math

import numpy as np

from coral_city.sensing import GRAVITY, SURFACE_PRESSURE_PA, Navigator, rotation_of


def test_depth_comes_from_pressure():
    n = Navigator(density=1025.0)
    n.pressure(SURFACE_PRESSURE_PA + 1025.0 * GRAVITY * 7.0)
    n.imu((1, 0, 0, 0), (0, 0, 0))
    assert n.observation(0.0).depth == pytest_approx(7.0)


def test_heading_comes_from_the_attitude():
    n = Navigator()
    half = math.radians(30) / 2
    n.pressure(SURFACE_PRESSURE_PA)
    n.imu((math.cos(half), 0, 0, math.sin(half)), (0, 0, 0.1))
    seen = n.observation(0.0)
    assert seen.heading == pytest_approx(math.radians(30))
    assert seen.velocity[5] == pytest_approx(0.1)


def test_position_is_reckoned_from_the_dvl_and_the_heading():
    n = Navigator()
    half = math.radians(90) / 2
    n.pressure(SURFACE_PRESSURE_PA)
    n.imu((math.cos(half), 0, 0, math.sin(half)), (0, 0, 0))
    n.dvl((1.0, 0.0, 0.0))     # a metre per second ahead, while pointing along +y
    n.observation(0.0)
    seen = n.observation(2.0)
    assert seen.position[0] == pytest_approx(0.0, abs=1e-9)
    assert seen.position[1] == pytest_approx(2.0)
    assert seen.estimated


def test_rotation_of_identity():
    assert np.allclose(rotation_of(1, 0, 0, 0), np.eye(3))


def pytest_approx(value, abs=1e-6):
    import pytest
    return pytest.approx(value, abs=abs)
