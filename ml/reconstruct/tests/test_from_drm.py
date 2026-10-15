"""The rebuild's frame is a rotation, never a mirror."""

import numpy as np

from iocean_reconstruct.from_drm import level_and_scale


def test_the_levelled_frame_keeps_the_reefs_handedness():
    rng = np.random.default_rng(0)
    for seed in range(20):
        r = np.random.default_rng(seed)
        reef = np.c_[r.uniform(-10, 10, 4000), r.uniform(-2, 2, 4000), r.normal(0, 0.1, 4000)]
        turn, _ = np.linalg.qr(r.normal(size=(3, 3)))
        if np.linalg.det(turn) < 0:
            turn[:, 0] *= -1
        cameras = np.c_[np.linspace(-9, 9, 50), np.zeros(50), np.full(50, 1.5)]
        frame = level_and_scale(reef @ turn.T, cameras @ turn.T)
        assert np.linalg.det(frame["rotation"]) > 0
