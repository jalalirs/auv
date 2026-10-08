"""Export a run for the places module: the U-Net as ONNX, and what it needs.

    iocean-depth export --run unet-v1-no-florida-20261007-1747

Writes runs/<run>/export/:
    model.onnx    the network: features in, depth and log variance out, any
                  batch, any size that is a multiple of 8
    model.json    the features in order and their normalisation, the calibrated
                  sigma scale, the cell size it was trained at, and where it
                  came from (run, commit, dataset, held-out results)

ONNX so a place can be built with onnxruntime on a CPU, without torch or a GPU.
The export is checked: onnxruntime and torch must agree on a chip to a
millimetre, or nothing is written.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import yaml


def export(run: pathlib.Path) -> dict:
    import onnxruntime as ort
    import torch

    from .data.dataset import FEATURES
    from .train import load_model

    model, mean, std = load_model(run, "cpu")
    model.eval()
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    info = json.loads((run / "run.json").read_text())
    report = json.loads((run / "report.json").read_text()) if (run / "report.json").is_file() else {}
    out = run / "export"
    out.mkdir(exist_ok=True)

    channels = len(FEATURES)
    dummy = torch.randn(1, channels, 128, 128)
    torch.onnx.export(model, (dummy,), str(out / "model.onnx"), input_names=["features"],
                      output_names=["depth", "log_variance"], opset_version=17, dynamo=False,
                      dynamic_axes={"features": {0: "batch", 2: "rows", 3: "columns"},
                                    "depth": {0: "batch", 1: "rows", 2: "columns"},
                                    "log_variance": {0: "batch", 1: "rows", 2: "columns"}})

    # Torch and onnxruntime on the same chip, normalised as a place will.
    x = np.random.default_rng(0).normal(size=(2, channels, 96, 160)).astype("float32")
    with torch.no_grad():
        td, tv = (t.numpy() for t in model(torch.from_numpy(x)))
    od, ov = ort.InferenceSession(str(out / "model.onnx"), providers=["CPUExecutionProvider"]).run(None, {"features": x})
    worst = float(max(np.abs(td - od).max(), np.abs(tv - ov).max()))
    if worst > 1e-3:
        (out / "model.onnx").unlink()
        raise ValueError(f"onnxruntime and torch disagree by {worst:.4g}; nothing exported")

    held = report.get("held-out", {})
    said = {
        "run": run.name, "commit": info.get("commit"), "dataset": cfg["dataset"],
        "features": list(FEATURES), "mean": mean.ravel().tolist(), "std": std.ravel().tolist(),
        "bands": (info.get("dataset", {}).get("manifest") or {}).get("bands")
                 or ["coastal", "blue", "green", "red", "rededge1", "nir", "swir16"],
        "cellM": 10.0, "chipCells": 128, "sizeMultipleOf": 8,
        "outputs": {"depth": "metres, positive down", "log_variance": "log of the variance of the depth, m^2"},
        "sigmaScale": report.get("sigmaScale", 1.0),
        "trainedOn": info.get("regions", {}).get("train"),
        "heldOut": {k: {"rmsM": v["unet"].get("rmsM"), "linearRmsM": v["linearBaseline"].get("rmsM")}
                    for k, v in held.items()},
        "redSea": ({"rmsM": report["redSea"]["unet"].get("rmsM"), "cells": report["redSea"]["unet"].get("cells")}
                   if report.get("redSea") else None),
        "onnxAgreesToM": round(worst, 6),
    }
    (out / "model.json").write_text(json.dumps(said, indent=1) + "\n")
    return said
