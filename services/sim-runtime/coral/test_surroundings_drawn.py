"""The seabed past the survey, as a mesh round the survey's own."""

import numpy as np

from draw import surroundings
from runner import Seabed


def a_seabed(across=100.0):
    heights = np.full((11, 11), -10.0, dtype="<f4")
    grid = np.full((8, 8), -40.0, dtype="<f4")
    return Seabed(heights, across, around=(grid, -2000.0, -2000.0, 2000.0, 2000.0))


def test_it_rings_the_survey_and_leaves_the_middle_to_it():
    seabed = a_seabed()
    points, faces = surroundings.mesh_of(seabed, reach_m=200.0)
    middle = points[faces].mean(axis=1)
    # Nothing wholly inside the survey's unblended square.
    inside = (np.abs(middle[:, 0]) < 40.0) & (np.abs(middle[:, 1]) < 40.0)
    assert not inside.any()
    assert np.abs(points[:, :2]).max() == 250.0


def test_it_lies_under_the_survey_where_they_overlap_and_on_gebco_past_it():
    seabed = a_seabed()
    points, _ = surroundings.mesh_of(seabed, reach_m=200.0)
    far = np.abs(points[:, :2]).max(axis=1) > 60.0
    assert np.allclose(points[far, 2], -40.0 - surroundings.SUNK_M, atol=1e-3)
    near = np.abs(points[:, :2]).max(axis=1) < 44.0
    assert np.all(points[near, 2] <= -10.0 - surroundings.SUNK_M + 1e-6)
