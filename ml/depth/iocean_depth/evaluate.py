"""Evaluate a run: on the regions it never saw, against the baseline, and in
the Red Sea.

Writes report.json and report.md into the run. Every number is against
something measured: the held-out regions' lidar, and in the Red Sea the cells
ICESat-2's tracks crossed. The baseline (models/linear.py) is fitted on the
run's own training chips, so the two are compared on equal terms.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import yaml

from .data import dataset as data
from .metrics import scores
from .models.linear import LinearBaseline
from .train import load_model, predict


def evaluate(run: pathlib.Path, ds: pathlib.Path) -> dict:
    import torch

    cfg = yaml.safe_load((run / "config.yaml").read_text())
    shallow, deep = cfg["target"]["shallowest_m"], cfg["target"]["deepest_m"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, mean, std = load_model(run, device)
    from . import config

    excluded = data.excluded_surveys(config.load(f"dataset/{cfg['dataset']}.yaml"))
    parts = data.split(data.load_chips(ds), cfg["split"]["test_regions"], cfg["split"]["validation_datasets"], excluded)
    baseline = LinearBaseline().fit(*data.arrays(parts["train"], shallow, deep))

    # The stated uncertainty, calibrated on the validation surveys: one factor
    # that makes 68% of their cells fall within one sigma, as an honest
    # Gaussian would, then applied unchanged to the held-out regions.
    Xv, Yv, Mv = data.arrays(parts["validation"], shallow, deep)
    dv, sv = predict(model, Xv, mean, std, device)
    ratio = (np.abs(dv - Yv) / np.maximum(sv, 1e-6))[Mv]
    sigma_scale = float(np.quantile(ratio, 0.6827)) if ratio.size else 1.0

    def both(rows):
        X, Y, M = data.arrays(rows, shallow, deep)
        depth, sigma = predict(model, X, mean, std, device)
        return {"unet": {**scores(depth, Y, M, sigma),
                         "calibrated": {k: v for k, v in scores(depth, Y, M, sigma * sigma_scale).items()
                                        if k in ("withinOneSigma", "medianSigmaM")}},
                "linearBaseline": scores(baseline.predict(X), Y, M)}

    report = {"run": run.name, "testRegions": cfg["split"]["test_regions"], "excluded": excluded,
              "sigmaScale": round(sigma_scale, 3), "held-out": {}, "validation": both(parts["validation"])}
    regions = sorted({r["region"] for r in parts["test"]})
    for region in regions:
        report["held-out"][region] = both([r for r in parts["test"] if r["region"] == region])
    if len(regions) > 1:
        report["held-out"]["all"] = both(parts["test"])
    report["bySurvey"] = {name: both([r for r in parts["test"] + parts["validation"] if r["dataset"] == name])
                          for name in sorted({r["dataset"] for r in parts["test"] + parts["validation"]})}
    if parts["red-sea"]:
        report["redSea"] = {**both(parts["red-sea"]), "labels": "ICESat-2 photons, the cells the tracks crossed"}
    (run / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    (run / "report.md").write_text(markdown(report))
    return report


def markdown(report: dict) -> str:
    def row(name, r):
        u, b = r["unet"], r["linearBaseline"]
        if not u.get("cells"):
            return f"| {name} | 0 | | | | |\n"
        cal = u.get("calibrated", {}).get("withinOneSigma", float("nan"))
        return (f"| {name} | {u['cells']:,} | {u['rmsM']:.2f} | {b['rmsM']:.2f} | {u['biasM']:+.2f} | "
                f"{u.get('withinOneSigma', float('nan')):.2f} | {cal:.2f} |\n")

    out = [f"# {report['run']}\n\n", "Depth error in metres against measured seabed, on regions the model never saw.\n\n",
           "| | cells | U-Net rms | linear rms | U-Net bias | within 1 sigma | calibrated |\n|---|---|---|---|---|---|---|\n"]
    for name, r in report["held-out"].items():
        out.append(row(name, r))
    out.append(row("validation (held-out surveys)", report["validation"]))
    if "redSea" in report:
        out.append(row("Red Sea (ICESat-2 tracks)", report["redSea"]))
    out.append("\nBy depth, all held-out regions, U-Net rms (linear rms):\n\n| depth | cells | U-Net | linear |\n|---|---|---|---|\n")
    every = report["held-out"].get("all") or next(iter(report["held-out"].values()))
    for u, b in zip(every["unet"]["byDepth"], every["linearBaseline"]["byDepth"]):
        out.append(f"| {u['fromM']} to {u['toM']} m | {u['cells']:,} | {u['rmsM']:.2f} | {b['rmsM']:.2f} |\n")
    out.append("\nBy survey (held out and validation):\n\n| survey | cells | U-Net rms | linear rms | U-Net bias |\n|---|---|---|---|---|\n")
    for name, r in report.get("bySurvey", {}).items():
        u, b = r["unet"], r["linearBaseline"]
        if u.get("cells"):
            out.append(f"| {name} | {u['cells']:,} | {u['rmsM']:.2f} | {b['rmsM']:.2f} | {u['biasM']:+.2f} |\n")
    if report.get("excluded"):
        out.append("\nExcluded: " + "; ".join(f"{k}: {v}" for k, v in report["excluded"].items()) + "\n")
    out.append(f"\nSigma scale from the validation surveys: {report.get('sigmaScale')}.\n")
    out.append("\n'Within 1 sigma' is the share of cells inside the model's own stated uncertainty: "
               "about 0.68 if that uncertainty is honest.\n")
    return "".join(out)
