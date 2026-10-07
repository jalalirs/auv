"""The baseline, the metrics and the U-Net."""

import numpy as np
import pytest

from iocean_depth.metrics import scores
from iocean_depth.models.linear import LinearBaseline


def test_scores_say_how_wrong_and_whether_the_sigma_is_honest():
    depth = np.full((1, 20, 20), 10.0)
    pred = depth + np.random.default_rng(0).normal(0, 1.0, depth.shape)
    mask = np.ones(depth.shape, bool)
    s = scores(pred, depth, mask, sigma=np.full(depth.shape, 1.0))
    assert 0.8 < s["rmsM"] < 1.2 and 0.6 < s["withinOneSigma"] < 0.76
    assert s["byDepth"][0]["fromM"] == 10 and s["cells"] == 400
    assert scores(pred, depth, np.zeros_like(mask))["cells"] == 0


def test_the_linear_baseline_recovers_a_linear_world():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(4, 9, 16, 16)).astype("float32")
    X[:, -1] = 1.0
    Y = (3.0 + 2.0 * X[:, 7] - 1.0 * X[:, 2]).astype("float32")
    M = np.ones(Y.shape, bool)
    b = LinearBaseline().fit(X, Y, M)
    assert np.abs(b.predict(X) - np.clip(Y, 0, None)).max() < 1e-3


def test_the_unet_gives_depth_and_its_variance_for_every_cell():
    torch = pytest.importorskip("torch")
    from iocean_depth.models.unet import UNet, gaussian_nll

    model = UNet(9, base=8)
    x = torch.randn(2, 9, 64, 64)
    depth, log_var = model(x)
    assert depth.shape == log_var.shape == (2, 64, 64)
    assert (depth >= 0).all() and (log_var.abs() <= 6).all()
    target = torch.full((2, 64, 64), 5.0)
    mask = torch.zeros((2, 64, 64), dtype=torch.bool)
    mask[:, 10:20, 10:20] = True
    loss = gaussian_nll(depth, log_var, target, mask)
    loss.backward()
    assert torch.isfinite(loss)


def test_a_small_unet_learns_a_slope():
    """A hundred steps on one chip whose depth is a slope across it: the error
    falls to under 40% of where it started (6.3 m to about 1.2 m by step 80)."""
    torch = pytest.importorskip("torch")
    from iocean_depth.models.unet import UNet

    torch.manual_seed(0)
    x = torch.linspace(0, 1, 32).repeat(32, 1)[None, None].repeat(1, 9, 1, 1)
    y = (2 + 10 * x[:, 0]).clone()
    model = UNet(9, base=8)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    first = None
    for _ in range(100):
        depth, _ = model(x)
        loss = (depth - y).abs().mean()
        first = first if first is not None else loss.item()
        opt.zero_grad(); loss.backward(); opt.step()
    assert loss.item() < 0.4 * first
