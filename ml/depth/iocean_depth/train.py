"""Train the depth model from a training config.

A run is a folder (runs/<run>/ under the data root) that says everything
about itself: config.yaml (the config as it was), run.json (the commit, the
dataset and its manifest, the device, the split, the best epoch), history.jsonl
(one line an epoch), model.pt (the best checkpoint by validation rms, with the
input normalisation it was trained with). evaluate.py writes report.json and
report.md beside them.

The first `warmup_epochs` train on the absolute error alone, then on the
Gaussian likelihood, so the variance is learnt on a depth that has settled.
"""

from __future__ import annotations

import json
import os
import pathlib
import time

import numpy as np
import yaml

from .data import dataset as data
from .metrics import scores


def predict(model, X: np.ndarray, mean: np.ndarray, std: np.ndarray, device: str, batch: int = 32):
    """Depth and its standard deviation for every cell of every chip in X."""
    import torch

    model.eval()
    depth, log_var = [], []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            d, lv = model(torch.from_numpy((X[i:i + batch] - mean) / std).to(device))
            depth.append(d.float().cpu().numpy()); log_var.append(lv.float().cpu().numpy())
    if not depth:
        return np.zeros((0,) + X.shape[2:], "float32"), np.zeros((0,) + X.shape[2:], "float32")
    return np.concatenate(depth), np.exp(0.5 * np.concatenate(log_var))


def load_model(run: pathlib.Path, device: str):
    import torch

    from .models.unet import UNet

    state = torch.load(run / "model.pt", map_location=device, weights_only=False)
    model = UNet(state["channels"], state["base"]).to(device)
    model.load_state_dict(state["model"])
    return model, state["mean"], state["std"]


def train(cfg: dict, run: pathlib.Path, ds: pathlib.Path) -> dict:
    import torch

    from .models.unet import UNet, gaussian_nll

    t = cfg["train"]
    torch.manual_seed(t["seed"])
    rng = np.random.default_rng(t["seed"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    run.mkdir(parents=True, exist_ok=False)
    (run / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    shallow, deep = cfg["target"]["shallowest_m"], cfg["target"]["deepest_m"]

    parts = data.split(data.load_chips(ds), cfg["split"]["test_regions"], cfg["split"]["validation_datasets"])
    Xtr, Ytr, Mtr = data.arrays(parts["train"], shallow, deep)
    Xva, Yva, Mva = data.arrays(parts["validation"], shallow, deep)
    flat = Xtr.transpose(1, 0, 2, 3).reshape(Xtr.shape[1], -1)
    mean = flat.mean(1)[None, :, None, None].astype("float32")
    std = (flat.std(1)[None, :, None, None] + 1e-6).astype("float32")
    mean[:, -1], std[:, -1] = 0.0, 1.0                      # "input present" stays 0 or 1

    model = UNet(Xtr.shape[1], cfg["model"]["base_channels"]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=t["learning_rate"], weight_decay=t["weight_decay"])
    per_epoch = int(np.ceil(len(Xtr) / t["batch"]))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=t["learning_rate"], total_steps=t["epochs"] * per_epoch)
    manifest = ds / "manifest.json"
    info = {"run": run.name, "commit": os.environ.get("GIT_COMMIT", "unknown"), "device": device,
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
            "dataset": {"name": ds.name, "manifest": json.loads(manifest.read_text()) if manifest.is_file() else None},
            "chips": {k: len(v) for k, v in parts.items()},
            "regions": {k: sorted({r["region"] for r in v}) for k, v in parts.items()},
            "parameters": int(sum(p.numel() for p in model.parameters())),
            "features": list(data.FEATURES), "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if info["dataset"]["manifest"]:
        info["dataset"]["manifest"].pop("configText", None)
    print(json.dumps({k: info[k] for k in ("run", "device", "gpu", "chips", "parameters")}), flush=True)

    best, t0 = None, time.time()
    for epoch in range(t["epochs"]):
        model.train()
        losses = []
        order = rng.permutation(len(Xtr))
        for i in range(0, len(order), t["batch"]):
            batch = [data.augment(Xtr[j], Ytr[j], Mtr[j], rng) for j in order[i:i + t["batch"]]]
            xb = torch.from_numpy((np.stack([b[0] for b in batch]) - mean) / std).to(device)
            yb = torch.from_numpy(np.stack([b[1] for b in batch])).to(device)
            mb = torch.from_numpy(np.stack([b[2] for b in batch])).to(device)
            if not mb.any():
                continue
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda" and t["precision"] == "bf16"):
                d, lv = model(xb)
            d, lv = d.float(), lv.float()
            loss = (d - yb).abs()[mb].mean() if epoch < t["warmup_epochs"] else gaussian_nll(d, lv, yb, mb)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            losses.append(loss.item())
        pv, sv = predict(model, Xva, mean, std, device)
        val = scores(pv, Yva, Mva, sv)
        line = {"epoch": epoch, "loss": round(float(np.mean(losses)), 4), "validationRmsM": val["rmsM"],
                "validationWithinOneSigma": val.get("withinOneSigma"), "seconds": round(time.time() - t0)}
        with open(run / "history.jsonl", "a") as out:
            out.write(json.dumps(line) + "\n")
        print(json.dumps(line), flush=True)
        if epoch >= t["warmup_epochs"] and (best is None or val["rmsM"] < best[0]):
            best = (val["rmsM"], epoch)
            torch.save({"model": model.state_dict(), "mean": mean, "std": std, "base": cfg["model"]["base_channels"],
                        "channels": int(Xtr.shape[1]), "features": list(data.FEATURES)}, run / "model.pt")
    info.update({"bestEpoch": best[1], "bestValidationRmsM": best[0],
                 "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0)})
    (run / "run.json").write_text(json.dumps(info, indent=1) + "\n")
    return info
