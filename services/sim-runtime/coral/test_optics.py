"""The camera between the water and the picture."""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import optics


def test_a_flat_port_narrows_a_gopro_by_about_a_quarter_and_a_dome_does_not():
    gopro = optics.Camera()
    across_flat, _ = optics.render_tangents(gopro, 160, 90)
    dome = optics.Camera(port=optics.Port("dome"))
    across_dome, _ = optics.render_tangents(dome, 160, 90)
    # 118 degrees across in air: behind a flat port in water about 80.
    in_water = 2 * math.degrees(math.atan(across_flat / 1.01))
    assert 75 < in_water < 85
    # Behind a dome nothing bends, and a fisheye's 118 degrees cannot be
    # drawn as a pinhole at all without the edge running away: wider still.
    assert across_dome > across_flat * 2


def test_the_middle_of_the_frame_looks_straight_ahead_and_the_edge_bends():
    camera = optics.Camera()
    (mx, my), _, _ = optics.maps(camera, 161, 91)
    assert abs(mx[45, 80] - 80) < 1e-3 and abs(my[45, 80] - 45) < 1e-3
    # The frame's top row looks further out at its ends than at its middle
    # (the corners are further off the axis), so in the pinhole picture it is
    # a curve that sags in the middle: which is how a straight line in the
    # world comes out bowed in a fisheye's frame.
    top = my[5, :]
    assert top[80] > top[5] + 1 and top[80] > top[155] + 1


def test_blue_bends_more_than_red_behind_a_flat_port_so_the_corners_fringe():
    (rx, _), _, (bx, _) = optics.maps(optics.Camera(), 161, 91)
    assert abs(rx[0, 0] - bx[0, 0]) > 0.05                   # corners, where it shows
    assert abs(rx[45, 80] - bx[45, 80]) < 1e-3               # not on the axis


def test_a_red_filter_warms_the_frame_and_keeps_its_brightness():
    rng = np.random.default_rng(0)
    frame = (np.clip(np.array([0.3, 0.5, 0.55]) + rng.normal(0, 0.05, (90, 160, 3)), 0, 1) * 255).astype("uint8")
    camera = optics.Camera(filter=optics.FILTERS["red"], port=optics.Port("none"), lens=optics.Lens(model="pinhole"))
    out = optics.through(frame, camera).astype(float)
    before = frame.reshape(-1, 3).mean(0)
    after = out.reshape(-1, 3).mean(0)
    assert after[0] / after[2] > before[0] / before[2] * 1.5
    luma = np.array([0.2126, 0.7152, 0.0722])
    assert abs(luma @ after - luma @ before) < 20
