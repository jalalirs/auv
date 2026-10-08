"""Fine-tune the cover model on photo-quadrats labelled at points, and check it
on countries it never saw.

The survey's points say a group (hard coral, soft coral, algae, sand...), not
one of the model's 95 classes, so the model is taught at the group level: at
each labelled point, the log of the summed probability of that group's classes.
The encoder learns at `learning_rate`, the decode head at ten times it.

A run is a folder, runs/<run>/ under the data root: config.yaml, run.json,
history.jsonl, model/ (the best epoch by validation cover error, as Hugging
Face writes a model, so everything that runs the base model runs this), and
report.json and report.md: the base model and the fine-tuned one on the test
countries, side by side.

Scores are cover, as everywhere here: for each quadrat, each group's share of
its random points as the experts labelled them, against the model's (at the
same points, and over the whole photo, which is what a map counts).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import time

import numpy as np
import yaml

MAIN = ("hard_coral", "soft_coral", "algae", "sand")


def score(segmenter, groups, quadrats, allowed=None) -> dict:
    """Cover per quadrat, drawn against said, for each seabed group."""
    from .segment import gather_matrix

    gather = gather_matrix(groups, segmenter.id2label)
    ns = groups.names.index("not_seabed")
    G = len(groups.names)
    drawn, at_points, dense = [], [], []
    right = total = 0
    for q in quadrats:
        g = segmenter.probabilities(q.image, into=gather, allowed=allowed).argmax(0).cpu().numpy()
        keep = q.random & (q.group != ns)
        if not keep.any():
            continue
        cols = np.clip(np.round(q.xy[keep, 0]).astype(int), 0, g.shape[1] - 1)
        rows = np.clip(np.round(q.xy[keep, 1]).astype(int), 0, g.shape[0] - 1)
        said = g[rows, cols]
        truth = q.group[keep]
        right += int((said == truth).sum())
        total += int(keep.sum())
        drawn.append(np.bincount(truth, minlength=G) / keep.sum())
        s = said[said != ns]
        at_points.append(np.bincount(s, minlength=G) / max(len(s), 1))
        d = g[g != ns]
        dense.append(np.bincount(d.ravel(), minlength=G) / max(d.size, 1))
    drawn, at_points, dense = np.array(drawn), np.array(at_points), np.array(dense)
    out = {"quadrats": len(drawn), "pointAccuracy": round(right / max(total, 1), 4), "groups": {}}
    for name in groups.seabed:
        k = groups.names.index(name)
        d = drawn[:, k]
        row = {"meanDrawn": round(float(d.mean()), 4)}
        for label, said in (("atPoints", at_points[:, k]), ("dense", dense[:, k])):
            row[label] = {"meanSaid": round(float(said.mean()), 4),
                          "meanAbsError": round(float(np.abs(said - d).mean()), 4),
                          "bias": round(float((said - d).mean()), 4),
                          "correlation": (round(float(np.corrcoef(d, said)[0, 1]), 3)
                                          if d.std() > 0 and said.std() > 0 else None)}
        out["groups"][name] = row
    out["mainMeanAbsError"] = round(float(np.mean([out["groups"][n]["dense"]["meanAbsError"] for n in MAIN])), 4)
    return out


def _batch(quadrats, crop: int, rng):
    """Random crops, quarter turns and flips of a batch; the points moved with them."""
    images, points = [], []
    for q in quadrats:
        n = q.image.shape[0]
        r0, c0 = rng.integers(0, n - crop + 1, 2)
        image = q.image[r0:r0 + crop, c0:c0 + crop]
        x, y = q.xy[:, 0] - c0, q.xy[:, 1] - r0
        inside = (x >= 0) & (x <= crop - 1) & (y >= 0) & (y <= crop - 1)
        x, y, g = x[inside], y[inside], q.group[inside]
        for _ in range(rng.integers(0, 4)):          # a quarter turn anticlockwise
            image = np.rot90(image)
            x, y = y, crop - 1 - x
        if rng.random() < 0.5:
            image = image[:, ::-1]
            x = crop - 1 - x
        images.append(np.ascontiguousarray(image))
        points.append((np.round(y).astype(int), np.round(x).astype(int), g))
    return np.stack(images), points


def train(cfg: dict, base_cfg: dict, base: pathlib.Path, run: pathlib.Path, data_root: pathlib.Path) -> dict:
    import torch
    import torch.nn.functional as F
    from transformers import SegformerForSemanticSegmentation

    from . import seaview
    from .classes import Groups
    from .segment import Segmenter, gather_matrix, seabed_only

    t = cfg["train"]
    rng = np.random.default_rng(t["seed"])
    torch.manual_seed(t["seed"])
    run.mkdir(parents=True, exist_ok=False)
    (run / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    seg = Segmenter(base, window=base_cfg["window"], stride=base_cfg["stride"])
    groups = Groups(seg.id2label, base_cfg["groups"])
    allowed = seabed_only(groups, seg.id2label)
    t0 = time.time()
    parts = seaview.split(seaview.load(data_root / cfg["data"]["root"], cfg, groups),
                          cfg["split"]["test"], cfg["split"]["validation"])
    print(json.dumps({k: len(v) for k, v in parts.items()} | {"loadSeconds": round(time.time() - t0)}), flush=True)

    device = seg.device
    model = SegformerForSemanticSegmentation.from_pretrained(base).to(device)
    head = [p for n, p in model.named_parameters() if n.startswith("decode_head")]
    body = [p for n, p in model.named_parameters() if not n.startswith("decode_head")]
    lr = float(t["learning_rate"])
    opt = torch.optim.AdamW([{"params": body, "lr": lr}, {"params": head, "lr": lr * 10}],
                            weight_decay=float(t["weight_decay"]))
    steps = t["epochs"] * int(np.ceil(len(parts["train"]) / t["batch"]))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[lr, lr * 10], total_steps=steps, pct_start=0.1)
    gather = torch.from_numpy(gather_matrix(groups, seg.id2label)).to(device)
    ns = groups.names.index("not_seabed")

    info = {"run": run.name, "base": str(base), "commit": os.environ.get("GIT_COMMIT", "unknown"),
            "quadrats": {k: len(v) for k, v in parts.items()},
            "countries": {k: sorted({q.country for q in v}) for k, v in parts.items()},
            "points": {k: int(sum(len(q.group) for q in v)) for k, v in parts.items()},
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    best = None
    for epoch in range(t["epochs"]):
        model.train()
        losses = []
        order = rng.permutation(len(parts["train"]))
        for i in range(0, len(order), t["batch"]):
            images, points = _batch([parts["train"][j] for j in order[i:i + t["batch"]]], t["crop"], rng)
            x = torch.from_numpy(images).to(device).permute(0, 3, 1, 2).float() / 255.0
            x = (x - seg.mean) / seg.std
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda" and t["precision"] == "bf16"):
                logits = model(pixel_values=x).logits
            p = F.interpolate(logits.float(), size=x.shape[2:], mode="bilinear", align_corners=False).softmax(1)
            terms = []
            for b, (rows, cols, g) in enumerate(points):
                keep = g != ns
                if not keep.any():
                    continue
                r, c, gg = (torch.from_numpy(v[keep]).to(device) for v in (rows, cols, g))
                at = p[b][:, r, c]                                   # (classes, points)
                group_p = (gather[gg] * at.T).sum(1)                 # each point's own group
                terms.append(-torch.log(group_p.clamp_min(1e-6)))
            if not terms:
                continue
            loss = torch.cat(terms).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            losses.append(loss.item())
        model.eval()
        seg.model = model
        val = score(seg, groups, parts["validation"], allowed)
        line = {"epoch": epoch, "loss": round(float(np.mean(losses)), 4), "validationMainError": val["mainMeanAbsError"],
                "validationPointAccuracy": val["pointAccuracy"], "seconds": round(time.time() - t0)}
        with open(run / "history.jsonl", "a") as out:
            out.write(json.dumps(line) + "\n")
        print(json.dumps(line), flush=True)
        if best is None or val["mainMeanAbsError"] < best[0]:
            best = (val["mainMeanAbsError"], epoch)
            model.save_pretrained(run / "model")
            shutil.copy(base / "preprocessor_config.json", run / "model" / "preprocessor_config.json")

    info.update({"bestEpoch": best[1], "bestValidationMainError": best[0], "seconds": round(time.time() - t0),
                 "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    (run / "run.json").write_text(json.dumps(info, indent=1) + "\n")

    # The base model and the best epoch on the countries neither saw.
    report = {"testCountries": info["countries"]["test"]}
    for label, folder in (("base", base), ("fineTuned", run / "model")):
        one = Segmenter(folder, window=base_cfg["window"], stride=base_cfg["stride"])
        report[label] = score(one, groups, parts["test"], allowed)
    (run / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    (run / "report.md").write_text(markdown(report))
    return info


def markdown(r: dict) -> str:
    lines = [f"# Caribbean photo-quadrats from {', '.join(r['testCountries'])}, countries neither model saw", "",
             f"{r['base']['quadrats']} quadrats. Point accuracy (the group at each expert's point): base "
             f"{r['base']['pointAccuracy']:.1%}, fine-tuned {r['fineTuned']['pointAccuracy']:.1%}.", "",
             "Cover per quadrat (each group's share of the seabed), over the whole photo, as a map counts it:", "",
             "| group | drawn | base says | base error | fine-tuned says | fine-tuned error | fine-tuned correlation |",
             "|---|---|---|---|---|---|---|"]
    for name, b in r["base"]["groups"].items():
        f = r["fineTuned"]["groups"][name]
        lines.append(f"| {name} | {b['meanDrawn']:.1%} | {b['dense']['meanSaid']:.1%} | {b['dense']['meanAbsError']:.1%} | "
                     f"{f['dense']['meanSaid']:.1%} | {f['dense']['meanAbsError']:.1%} | {f['dense']['correlation']} |")
    return "\n".join(lines) + "\n"
