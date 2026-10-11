"""The calibration recovers a lens it was not told: checkerboards drawn through
a known fisheye, at poses across the frame, fitted back."""

import importlib.machinery
import importlib.util
import math
import pathlib

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

HERE = pathlib.Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("calibrate_camera", str(HERE / "calibrate-camera"))
spec = importlib.util.spec_from_loader("calibrate_camera", loader)
calibrate_camera = importlib.util.module_from_spec(spec)
loader.exec_module(calibrate_camera)

WIDE, TALL = 960, 540
K = np.array([[460.0, 0, 482.0], [0, 460.0, 268.0], [0, 0, 1]])
D = np.array([0.04, -0.02, 0.01, -0.003])
PATTERN, SQUARE = (9, 6), 0.025


def board_seen(rvec, tvec) -> np.ndarray:
    """A 10 by 7 board of 25 mm squares, as this lens sees it at this pose."""
    us, vs = np.meshgrid(np.arange(WIDE, dtype=np.float64), np.arange(TALL, dtype=np.float64))
    pixels = np.stack([us.ravel(), vs.ravel()], -1).reshape(-1, 1, 2)
    rays = cv2.fisheye.undistortPoints(pixels, K, D).reshape(-1, 2)
    rays = np.concatenate([rays, np.ones((len(rays), 1))], 1)
    R, _ = cv2.Rodrigues(rvec)
    # The board plane z = 0 in its own frame: n . (X - t) = 0 with n = R e3.
    n = R[:, 2]
    t = np.asarray(tvec, dtype=float).ravel()
    depth = (n @ t) / (rays @ n)
    hits = rays * depth[:, None]
    local = (hits - t) @ R                      # into the board's frame
    # Squares from -1 to 9 across and -1 to 6 down, so the inner corners are
    # at 0..8 by 0..5 squares, which is where calibrate-camera puts them.
    i = np.floor(local[:, 0] / SQUARE + 1).astype(int)
    j = np.floor(local[:, 1] / SQUARE + 1).astype(int)
    inside = (depth > 0) & (i >= 0) & (i < 10) & (j >= 0) & (j < 7)
    image = np.full(len(rays), 128, np.uint8)
    image[inside] = np.where((i[inside] + j[inside]) % 2 == 0, 30, 225)
    # A white margin round the board, as a printed one has.
    margin = (depth > 0) & ~inside & (i >= -1) & (i < 11) & (j >= -1) & (j < 8)
    image[margin] = 225
    return cv2.GaussianBlur(image.reshape(TALL, WIDE), (3, 3), 0.8)


def test_a_lens_comes_back_from_boards_seen_through_it(tmp_path):
    rng = np.random.default_rng(3)
    written = 0
    for k in range(48):
        # Across the frame: the board's middle aimed at a spread of angles.
        aim = np.array([rng.uniform(-0.9, 0.9), rng.uniform(-0.5, 0.5), 1.0])
        distance = rng.uniform(0.35, 0.6)
        centre = aim / np.linalg.norm(aim) * distance
        rvec = np.array([rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3)])
        R, _ = cv2.Rodrigues(rvec)
        middle = np.array([4 * SQUARE, 2.5 * SQUARE, 0.0])
        tvec = centre - R @ middle
        cv2.imwrite(str(tmp_path / f"{k:03d}.png"), board_seen(rvec, tvec))
        written += 1
    said = calibrate_camera.calibrate([tmp_path], PATTERN, 25.0, medium="air", say=lambda *_: None)
    true_fov = calibrate_camera.field_of_view(K, D, (WIDE, TALL))
    assert said["views"] >= 10
    assert said["reprojectionErrorPx"] < 0.5
    assert abs(said["horizontalFovDeg"] - true_fov) < 1.0, (said["horizontalFovDeg"], true_fov)
    focal = said["focalOfHalfWidth"][0] * (WIDE - 1) / 2
    assert abs(focal - K[0, 0]) / K[0, 0] < 0.02, focal
    assert said["kind"] == "measured" and "checkerboard" in said["from"]
