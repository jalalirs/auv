"""A built dataset read back for training: chips, splits, inputs and targets.

The split is by region, and checked: a region in both training and test is an
error, not a warning, because neighbouring cells are alike and a model scored
on the reefs it trained on is scored on its memory.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

# The features are computed in the places module, beside the band reader, so
# that a place sees exactly what the model was trained on.
from iocean_places.fetch.sentinel_bands import FEATURES, features


def load_chips(ds: pathlib.Path) -> list[dict]:
    rows = [json.loads(line) for line in (ds / "chips" / "index.jsonl").read_text().splitlines() if line.strip()]
    out = []
    for r in rows:
        folder = r["region"].replace(" ", "-").replace("/", "-").lower()
        d = np.load(ds / "chips" / folder / r["file"])
        out.append({**r, "x": d["x"], "y": d["y"]})
    return out


def target(y: np.ndarray, shallowest: float, deepest: float) -> tuple[np.ndarray, np.ndarray]:
    """Depth, positive down, and which cells count: measured seabed between
    `shallowest` and `deepest` metres."""
    depth = -y
    mask = np.isfinite(depth) & (depth > shallowest) & (depth < deepest)
    return np.where(mask, depth, 0.0).astype("float32"), mask


def split(rows: list[dict], test_regions, validation_datasets, excluded=()) -> dict[str, list[dict]]:
    """`excluded` are surveys whose labels are not to be trusted (a dataset
    config's `excluded:`), out of every part."""
    out = {"train": [], "validation": [], "test": [], "red-sea": []}
    for r in rows:
        if r["dataset"] in excluded:
            continue
        if r["region"] == "Red Sea":
            out["red-sea"].append(r)
        elif r["region"] in test_regions:
            out["test"].append(r)
        elif r["dataset"] in validation_datasets:
            out["validation"].append(r)
        else:
            out["train"].append(r)
    leaked = {r["region"] for r in out["train"]} & {r["region"] for r in out["test"]}
    if leaked:
        raise ValueError(f"regions in both training and test: {sorted(leaked)}")
    shared = {r["dataset"] for r in out["train"]} & {r["dataset"] for r in out["validation"]}
    if shared:
        raise ValueError(f"surveys in both training and validation: {sorted(shared)}")
    return out


def arrays(rows: list[dict], shallowest: float, deepest: float):
    if not rows:
        return np.zeros((0, len(FEATURES), 1, 1), "float32"), np.zeros((0, 1, 1), "float32"), np.zeros((0, 1, 1), bool)
    X = np.stack([features(r["x"]) for r in rows])
    Y, M = zip(*(target(r["y"], shallowest, deepest) for r in rows))
    return X, np.stack(Y), np.stack(M)


def augment(x: np.ndarray, y: np.ndarray, m: np.ndarray, rng: np.random.Generator):
    """A quarter turn and a mirror, at random: a reef is a reef whichever way north is."""
    k = int(rng.integers(4))
    x, y, m = np.rot90(x, k, (-2, -1)), np.rot90(y, k, (-2, -1)), np.rot90(m, k, (-2, -1))
    if rng.random() < 0.5:
        x, y, m = x[..., ::-1], y[..., ::-1], m[..., ::-1]
    return np.ascontiguousarray(x), np.ascontiguousarray(y), np.ascontiguousarray(m)


def excluded_surveys(dataset_cfg: dict) -> dict[str, str]:
    """The surveys a dataset config excludes, and why."""
    return {d["slug"]: d["excluded"] for d in dataset_cfg.get("lidar", []) if d.get("excluded")}
