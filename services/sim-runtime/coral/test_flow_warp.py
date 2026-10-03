"""The water grid's step on Warp is the numpy step, to float precision."""

import numpy as np
import pytest

from systems import flow as F
from systems import flow_warp

pytestmark = pytest.mark.skipif(not flow_warp.available(), reason="no Warp here")


def a_stirred_grid(n=(24, 20, 16), seed=0):
    rng = np.random.default_rng(seed)
    u = rng.normal(0.0, 0.05, n + (3,))
    jets = np.zeros_like(u)
    jets[8:14, 8:12, 6:10] = [0.6, 0.0, 0.1]
    solid = np.zeros(n, dtype=bool)
    solid[:, :, :3] = True                      # a floor
    solid[18:22, 4:8, :9] = True                # a rock
    return u, jets, solid


def numpy_step(u, jets, solid, pressure, cell, dt):
    pushing = np.linalg.norm(jets, axis=-1, keepdims=True) > 1e-4
    u = u + np.where(pushing, (jets - u) * min(1.0, F.PULL * dt), 0.0)
    g = np.indices(u.shape[:3]).reshape(3, -1).T.astype(float)
    back = g - u.reshape(-1, 3) * dt / cell
    u = F.sample(u, back).reshape(u.shape)
    u *= (1.0 - F.DECAY * dt)
    return F.project(u, solid, cell, iterations=F.WARM, pressure=pressure)


def test_one_step_is_the_numpy_step():
    u, jets, solid = a_stirred_grid()
    want_u, want_p = numpy_step(u, jets, solid, None, 0.05, 0.05)
    got_u, got_p = flow_warp.step(u, jets, solid, None, 0.05, 0.05, F.PULL, F.DECAY, F.WARM, where="cpu")
    assert np.abs(got_u - want_u).max() < 1e-5
    assert np.abs(got_p - want_p).max() < 1e-6


def test_twenty_steps_stay_the_numpy_steps():
    u, jets, solid = a_stirred_grid(seed=3)
    nu, npre, wu, wpre = u.copy(), None, u.copy(), None
    for k in range(20):
        on = jets if k < 10 else None
        nu, npre = numpy_step(nu, on if on is not None else np.zeros_like(nu), solid, npre, 0.05, 0.05)
        wu, wpre = flow_warp.step(wu, on, solid, wpre, 0.05, 0.05, F.PULL, F.DECAY, F.WARM, where="cpu")
    assert np.abs(wu - nu).max() < 1e-4
