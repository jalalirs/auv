"""The vehicle's wash, against the numbers the jet model was taken from."""

import math

import numpy as np

from systems.wash import Wash, WashSystem
from systems.build import the_ocean


class Unit:
    def __init__(self, position, direction, forward=51.5, reverse=40.0):
        self.position, self.direction = np.array(position, float), np.array(direction, float)
        self.max_forward_n, self.max_reverse_n = forward, reverse


def a_t200(command, direction=(1.0, 0.0, 0.0)):
    """One T200 on a vehicle at the origin, pointing along x, a metre down."""
    world = the_ocean(None, 1, 0.005)
    world.vehicle.position = np.array([0.0, 0.0, -1.0])
    world.thrust.diameter_m = 0.076
    world.thrust.commands = np.array([command])
    system = WashSystem([Unit((0.0, 0.0, 0.0), direction)])
    system.step(world)
    return world.wash


def test_a_t200_at_full_power_leaves_at_about_four_and_a_half_metres_a_second():
    wash = a_t200(1.0)
    assert 4.3 < wash.efflux[0] < 4.9, wash.efflux


def test_a_metre_on_it_is_still_about_seven_tenths():
    """Pushing the vehicle along +x pushes the water along -x."""
    wash = a_t200(1.0)
    u = wash.at([[-1.0, 0.0, -1.0]])[0]
    assert u[0] < 0 and 0.55 < -u[0] < 0.85, u


def test_nothing_comes_out_of_a_thruster_that_is_not_pushing():
    wash = a_t200(0.0)
    assert not wash.at([[-0.5, 0.0, -1.0], [0.5, 0.0, -1.0]]).any()


def test_reversed_it_blows_the_other_way():
    wash = a_t200(-1.0)
    assert wash.at([[0.5, 0.0, -1.0]])[0][0] > 0.3
    assert not wash.at([[-0.5, 0.0, -1.0]]).any(), "nothing upstream of the propeller"


def test_it_is_strongest_on_its_axis_and_falls_away_to_the_side():
    wash = a_t200(1.0)
    on, off, far = wash.at([[-0.6, 0.0, -1.0], [-0.6, 0.08, -1.0], [-0.6, 0.3, -1.0]])
    assert abs(on[0]) > abs(off[0]) > abs(far[0])
    assert abs(far[0]) < 0.01 * abs(on[0])


def test_a_jet_follows_the_vehicle_round():
    """Turned to face +y, the same thruster blows along -y."""
    world = the_ocean(None, 1, 0.005)
    world.thrust.diameter_m = 0.076
    world.thrust.commands = np.array([1.0])
    c, s = math.cos(math.pi / 2), math.sin(math.pi / 2)
    world.vehicle.rotation = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    WashSystem([Unit((0.1, 0.0, 0.0), (1.0, 0.0, 0.0))]).step(world)
    u = world.wash.at([[0.0, -0.5, 0.0]])[0]
    assert u[1] < -0.5 and abs(u[0]) < 1e-6
