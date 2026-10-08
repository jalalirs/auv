"""Upright and to scale: a tilted plane seen from cameras above it comes back
flat, with the cameras at the height asked for."""

import sys
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from iocean_reconstruct.patch import frame_of, rasterise


def test_a_tilted_reef_comes_back_level_with_its_cameras_above():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(-10, 10, 4000), rng.uniform(-2, 2, 4000)
    z = 0.05 * rng.normal(size=4000)
    tilt = np.array([[1, 0, 0], [0, np.cos(0.4), -np.sin(0.4)], [0, np.sin(0.4), np.cos(0.4)]])
    points = np.column_stack([x, y, z]) @ tilt.T * 3.0 + [5, -2, 7]          # tilted, scaled, moved
    cams = np.column_stack([np.linspace(-9, 9, 30), np.zeros(30), np.full(30, 0.5)]) @ tilt.T * 3.0 + [5, -2, 7]
    centre, rotation, heights = frame_of(points, cams)
    flat = (points - centre) @ rotation.T
    assert np.std(flat[:, 2]) < 0.2 and np.ptp(flat[:, 0]) > 50              # level, and x the long way
    assert np.allclose(heights, 1.5, atol=0.2)                                  # cameras above, not below
    scale = 1.5 / np.median(heights)
    assert abs(np.median(((cams - centre) @ rotation.T * scale)[:, 2]) - 1.5) < 1e-6


def test_the_highest_point_wins_a_cell():
    pts = np.array([[0.0, 0.0, 1.0], [0.004, 0.004, 2.0], [0.5, 0.5, 0.0]])
    rgb = np.array([[10, 10, 10], [200, 200, 200], [50, 50, 50]], np.uint8)
    h, c, lo = rasterise(pts, rgb, 0.01)
    assert h[-1, 0] == 2.0 and (c[-1, 0] == 200).all()
    assert np.isnan(h).sum() == h.size - 2
