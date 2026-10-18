"""A reconstruction's own ground laid into its place's."""

import math

import numpy as np

from runner import Seabed, Surface


def _flat_place(depth=-10.0):
    return Seabed(np.full((65, 65), depth, dtype="<f4"), 640.0)


def test_inside_a_surface_the_bottom_is_its_ground():
    grid = np.full((41, 201), -8.0)               # 2 m high above the place, 10 m by 2 m at 5 cm
    seabed = _flat_place()
    seabed.surfaces = [Surface(grid, (0.0, 0.0), 0.0, 0.05, feather=0.5)]
    assert abs(seabed.under(5.0, 1.0) - (-8.0)) < 1e-6
    assert abs(seabed.under(50.0, 50.0) - (-10.0)) < 1e-6


def test_it_fades_into_the_place_at_its_edge():
    seabed = _flat_place()
    seabed.surfaces = [Surface(np.full((41, 201), -8.0), (0.0, 0.0), 0.0, 0.05, feather=1.0)]
    mid = seabed.under(0.5, 1.0)                  # half a metre in from the west edge
    assert -9.5 < mid < -8.5


def test_unmeasured_cells_leave_the_place_as_it_was():
    grid = np.full((41, 201), -8.0)
    grid[:, 100:] = np.nan
    seabed = _flat_place()
    seabed.surfaces = [Surface(grid, (0.0, 0.0), 0.0, 0.05, feather=0.2)]
    assert abs(seabed.under(8.0, 1.0) - (-10.0)) < 1e-6


def test_a_surface_turned_by_its_heading():
    grid = np.full((41, 201), -8.0)               # long axis 10 m, laid north
    seabed = _flat_place()
    seabed.surfaces = [Surface(grid, (0.0, 0.0), 90.0, 0.05, feather=0.2)]
    assert abs(seabed.under(-1.0, 5.0) - (-8.0)) < 1e-6
    assert abs(seabed.under(5.0, 1.0) - (-10.0)) < 1e-6


def test_many_points_and_the_slope_on_it():
    x = np.linspace(0.0, 10.0, 41)
    grid = np.tile(-10.0 + 0.2 * x, (41, 1))      # rises 0.2 m a metre eastward
    seabed = _flat_place()
    seabed.surfaces = [Surface(grid, (0.0, 0.0), 0.0, 0.25, feather=0.2)]
    many = seabed.under_many(np.array([5.0, 50.0]), np.array([5.0, 5.0]))
    assert abs(many[0] - (-9.0)) < 1e-6 and abs(many[1] - (-10.0)) < 1e-6
    n = seabed.normal(5.0, 5.0)
    assert abs(n[0] - (-0.2 / math.sqrt(1.04))) < 1e-3
    assert seabed.normal_many(np.array([5.0]), np.array([5.0])).shape == (1, 3)
