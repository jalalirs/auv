"""The depth model: a U-Net from Sentinel-2 to depth and how sure it is.

    python -m iocean_places.training.depth_model train --root ~/iocean/training/depth-v1 --run v1
    python -m iocean_places.training.depth_model train --test-regions Florida --run v1-no-florida

Spatial on purpose: a reef's depth is read off its shape as much as its colour
(a flat beside a crest beside a slope, a dark patch in sand), which a per-pixel
model cannot see. Each chip is 128 cells of 10 m, so every prediction sees
about 1.3 km around it.

Out come two numbers per cell: the depth, and the log of its variance, trained
together on the Gaussian likelihood of the measured depth, so the model says
where it is unsure; that variance is what a place's weak map gets. Only cells
something measured count, so a chip half covered by lidar trains on its half,
and ICESat-2's tracks train on the cells they crossed.

Tested only on regions it never saw: neighbouring cells are alike, and a model
scored on random cells of the reefs it trained on would be scored on its own
memory. The baseline is the per-pixel linear fit the current colour model is
built on (the log-ratio and the log of each band), fitted on the same training
cells: what the U-Net has to beat.

Needs torch (the box's ~/iocean/train-venv); the rest of the package does not.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np

ROOT = pathlib.Path.home() / "iocean" / "training" / "depth-v1"
TEST_REGIONS = ("USVI", "Guam/CNMI", "Am. Samoa")
# Held out of training to choose the epoch, one survey from each of the two
# biggest training regions, so the choice is not made on the training reefs.
VALIDATION_DATASETS = ("FL_DryTortugas_NGS_DEM_2015_6212", "USACE_Kauai_HI_LMSL_DEM_2013_9335")
DEEPEST, SHALLOWEST = 40.0, 0.0
BANDS_BY_DEPTH = ((0, 5), (5, 10), (10, 15), (15, 20), (20, 40))


# ── data ─────────────────────────────────────────────────────────────────────

def load(root: pathlib.Path) -> list[dict]:
    rows = [json.loads(line) for line in (root / "chips" / "index.jsonl").read_text().splitlines() if line.strip()]
    out = []
    for r in rows:
        folder = r["region"].replace(" ", "-").replace("/", "-").lower()
        d = np.load(root / "chips" / folder / r["file"])
        out.append({**r, "x": d["x"], "y": d["y"]})
    return out


def features(x: np.ndarray) -> np.ndarray:
    """The seven band medians as the network sees them: the log of each band,
    Stumpf's log-ratio of blue to green, and where the input is missing."""
    valid = np.all(np.isfinite(x), axis=0)
    safe = np.where(np.isfinite(x), np.clip(x, 1e-4, None), 1e-4)
    logs = np.log(safe)
    ratio = np.log(1000 * safe[1]) / np.log(1000 * safe[2])
    return np.concatenate([logs, ratio[None], valid[None].astype("float32")]).astype("float32")


def target(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Depth (positive down) and which cells count: measured seabed between
    the surface and DEEPEST."""
    depth = -y
    mask = np.isfinite(depth) & (depth > SHALLOWEST) & (depth < DEEPEST)
    return np.where(mask, depth, 0.0).astype("float32"), mask


def split(rows: list[dict], test_regions, validation) -> dict[str, list[dict]]:
    out = {"train": [], "validation": [], "test": [], "red-sea": []}
    for r in rows:
        if r["region"] == "Red Sea":
            out["red-sea"].append(r)
        elif r["region"] in test_regions:
            out["test"].append(r)
        elif r["dataset"] in validation:
            out["validation"].append(r)
        else:
            out["train"].append(r)
    return out


def arrays(rows: list[dict]):
    X = np.stack([features(r["x"]) for r in rows])
    Y, M = zip(*(target(r["y"]) for r in rows))
    return X, np.stack(Y), np.stack(M)


# ── the network ──────────────────────────────────────────────────────────────

def build_unet(channels: int, base: int = 32):
    import torch
    from torch import nn

    def block(a, b):
        return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.GroupNorm(8, b), nn.SiLU(),
                             nn.Conv2d(b, b, 3, padding=1), nn.GroupNorm(8, b), nn.SiLU())

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            w = [base, base * 2, base * 4, base * 8]
            self.down = nn.ModuleList([block(channels, w[0]), block(w[0], w[1]), block(w[1], w[2]), block(w[2], w[3])])
            self.pool = nn.MaxPool2d(2)
            self.up = nn.ModuleList([nn.ConvTranspose2d(w[3], w[2], 2, 2), nn.ConvTranspose2d(w[2], w[1], 2, 2),
                                     nn.ConvTranspose2d(w[1], w[0], 2, 2)])
            self.merge = nn.ModuleList([block(w[2] * 2, w[2]), block(w[1] * 2, w[1]), block(w[0] * 2, w[0])])
            self.head = nn.Conv2d(w[0], 2, 1)

        def forward(self, x):
            skips = []
            for i, d in enumerate(self.down):
                x = d(x)
                if i < 3:
                    skips.append(x)
                    x = self.pool(x)
            for up, merge, skip in zip(self.up, self.merge, reversed(skips)):
                x = merge(torch.cat([up(x), skip], 1))
            out = self.head(x)
            depth = nn.functional.softplus(out[:, 0])
            log_var = out[:, 1].clamp(-6, 6)
            return depth, log_var

    return UNet()


# ── training ─────────────────────────────────────────────────────────────────

def _augment(x, y, m, rng):
    k = rng.integers(4)
    x, y, m = np.rot90(x, k, (2, 3)), np.rot90(y, k, (1, 2)), np.rot90(m, k, (1, 2))
    if rng.random() < 0.5:
        x, y, m = x[..., ::-1], y[..., ::-1], m[..., ::-1]
    return np.ascontiguousarray(x), np.ascontiguousarray(y), np.ascontiguousarray(m)


def predict(model, X, mean, std, device, batch=32):
    import torch
    model.eval()
    out_d, out_v = [], []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            xb = torch.from_numpy((X[i:i + batch] - mean) / std).to(device)
            d, lv = model(xb)
            out_d.append(d.float().cpu().numpy()); out_v.append(lv.float().cpu().numpy())
    return np.concatenate(out_d), np.exp(0.5 * np.concatenate(out_v))


def scores(pred, sigma, depth, mask) -> dict:
    e = (pred - depth)[mask]
    d = depth[mask]
    out = {"cells": int(mask.sum()), "rmsM": round(float(np.sqrt(np.mean(e ** 2))), 3),
           "maeM": round(float(np.mean(np.abs(e))), 3), "biasM": round(float(np.mean(e)), 3)}
    if sigma is not None:
        s = sigma[mask]
        out["withinOneSigma"] = round(float(np.mean(np.abs(e) <= s)), 3)
        out["medianSigmaM"] = round(float(np.median(s)), 3)
    out["byDepth"] = []
    for lo, hi in BANDS_BY_DEPTH:
        b = (d >= lo) & (d < hi)
        if b.sum() > 100:
            out["byDepth"].append({"fromM": lo, "toM": hi, "cells": int(b.sum()),
                                   "rmsM": round(float(np.sqrt(np.mean(e[b] ** 2))), 3)})
    return out


def linear_baseline(Xtr, Ytr, Mtr):
    """Depth as a linear function of the log bands and the log-ratio, one fit
    over every training cell: the per-pixel colour model, global."""
    cols = list(range(8))
    A = Xtr[:, cols].transpose(0, 2, 3, 1)[Mtr & (Xtr[:, 8] > 0)]
    b = Ytr[Mtr & (Xtr[:, 8] > 0)]
    sample = np.random.default_rng(0).choice(len(b), min(len(b), 2_000_000), replace=False)
    A1 = np.c_[A[sample], np.ones(len(sample))]
    coef, *_ = np.linalg.lstsq(A1, b[sample], rcond=None)

    def apply(X):
        Z = X[:, cols].transpose(0, 2, 3, 1)
        return np.clip(Z @ coef[:-1] + coef[-1], 0, None)
    return apply


def train(root: pathlib.Path, run: str, test_regions, epochs: int, batch: int, lr: float, base: int, seed: int) -> dict:
    import torch

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    out = root / "models" / run
    out.mkdir(parents=True, exist_ok=True)
    rows = load(root)
    parts = split(rows, test_regions, VALIDATION_DATASETS)
    print({k: len(v) for k, v in parts.items()}, flush=True)
    Xtr, Ytr, Mtr = arrays(parts["train"])
    Xva, Yva, Mva = arrays(parts["validation"])
    flat = Xtr.transpose(1, 0, 2, 3).reshape(Xtr.shape[1], -1)
    mean = flat.mean(1)[None, :, None, None].astype("float32")
    std = (flat.std(1)[None, :, None, None] + 1e-6).astype("float32")
    mean[:, -1], std[:, -1] = 0.0, 1.0                      # the validity mask stays 0 or 1

    model = build_unet(Xtr.shape[1], base).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * int(np.ceil(len(Xtr) / batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
    best, history = None, []
    t0 = time.time()
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(Xtr))
        losses = []
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            xb, yb, mb = zip(*(_augment(Xtr[j:j + 1], Ytr[j:j + 1], Mtr[j:j + 1], rng) for j in idx))
            xb = torch.from_numpy((np.concatenate(xb) - mean) / std).to(device)
            yb = torch.from_numpy(np.concatenate(yb)).to(device)
            mb = torch.from_numpy(np.concatenate(mb)).to(device)
            if mb.sum() == 0:
                continue
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
                d, lv = model(xb)
            d, lv = d.float(), lv.float()
            # The first epochs on the error alone, then on the likelihood, so
            # the variance is learnt on a depth that has settled.
            if epoch < 5:
                loss = (torch.abs(d - yb))[mb].mean()
            else:
                loss = (0.5 * (torch.exp(-lv) * (d - yb) ** 2 + lv))[mb].mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
            losses.append(loss.item())
        pv, sv = predict(model, Xva, mean, std, device)
        val = scores(pv, sv, Yva, Mva)
        history.append({"epoch": epoch, "loss": round(float(np.mean(losses)), 4), "validationRmsM": val["rmsM"]})
        print(f"epoch {epoch:3d}  loss {np.mean(losses):7.4f}  validation rms {val['rmsM']:.3f} m  "
              f"({time.time() - t0:.0f} s)", flush=True)
        if epoch >= 5 and (best is None or val["rmsM"] < best[0]):
            best = (val["rmsM"], epoch)
            torch.save({"model": model.state_dict(), "mean": mean, "std": std, "base": base,
                        "channels": int(Xtr.shape[1])}, out / "model.pt")

    state = torch.load(out / "model.pt", weights_only=False)
    model.load_state_dict(state["model"])
    baseline = linear_baseline(Xtr, Ytr, Mtr)
    report = {"run": run, "testRegions": list(test_regions), "validationDatasets": list(VALIDATION_DATASETS),
              "chips": {k: len(v) for k, v in parts.items()}, "bestEpoch": best[1], "epochs": epochs,
              "history": history, "test": {}, "redSea": {}}
    for region in sorted({r["region"] for r in parts["test"]}) + ["all held-out regions"]:
        sel = [r for r in parts["test"] if region == "all held-out regions" or r["region"] == region]
        if not sel:
            continue
        X, Y, M = arrays(sel)
        p, s = predict(model, X, mean, std, device)
        report["test"][region] = {"unet": scores(p, s, Y, M), "linearBaseline": scores(baseline(X), None, Y, M)}
    if parts["red-sea"]:
        X, Y, M = arrays(parts["red-sea"])
        p, s = predict(model, X, mean, std, device)
        report["redSea"] = {"unet": scores(p, s, Y, M), "linearBaseline": scores(baseline(X), None, Y, M),
                            "labels": "ICESat-2 photons, the cells the tracks crossed"}
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="depth_model")
    ap.add_argument("step", choices=("train",))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--run", default="v1")
    ap.add_argument("--test-regions", nargs="+", default=list(TEST_REGIONS))
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--base", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    report = train(pathlib.Path(a.root).expanduser(), a.run, tuple(a.test_regions), a.epochs, a.batch, a.lr, a.base, a.seed)
    print(json.dumps({k: report[k] for k in ("bestEpoch", "test", "redSea")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
