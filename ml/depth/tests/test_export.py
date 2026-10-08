"""The model as the places module runs it: exported, windowed, blended."""

import json

import numpy as np
import pytest


def test_the_places_module_runs_the_export_as_torch_does(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("onnxruntime")
    import onnxruntime as ort
    from iocean_places.fetch.sentinel_bands import FEATURES, features
    from iocean_places.sources.learned import predict

    from iocean_depth.models.unet import UNet

    torch.manual_seed(0)
    model = UNet(len(FEATURES), base=8).eval()
    torch.onnx.export(model, (torch.randn(1, len(FEATURES), 128, 128),), str(tmp_path / "model.onnx"),
                      input_names=["features"], output_names=["depth", "log_variance"], opset_version=17, dynamo=False,
                      dynamic_axes={"features": {0: "b", 2: "r", 3: "c"}, "depth": {0: "b", 1: "r", 2: "c"},
                                    "log_variance": {0: "b", 1: "r", 2: "c"}})
    meta = {"mean": [0.0] * len(FEATURES), "std": [1.0] * len(FEATURES), "sigmaScale": 2.0}
    (tmp_path / "model.json").write_text(json.dumps(meta))
    session = ort.InferenceSession(str(tmp_path / "model.onnx"), providers=["CPUExecutionProvider"])

    rng = np.random.default_rng(0)
    x = rng.uniform(0.01, 0.1, (7, 128, 128)).astype("float32")
    depth, sigma = predict(session, meta, x)
    with torch.no_grad():
        d, lv = model(torch.from_numpy(features(x)[None]))
    assert np.allclose(depth, d[0].numpy(), atol=1e-3), "one window: the same as torch"
    assert np.allclose(sigma, 2.0 * np.exp(0.5 * lv[0].numpy()), rtol=1e-3), "sigma scaled by the calibration"

    big = rng.uniform(0.01, 0.1, (7, 201, 233)).astype("float32")
    big[:, 10:20, 30:40] = np.nan
    depth, sigma = predict(session, meta, big)
    assert depth.shape == (201, 233) and np.isnan(depth[10:20, 30:40]).all()
    assert np.isfinite(depth).sum() == 201 * 233 - 100
