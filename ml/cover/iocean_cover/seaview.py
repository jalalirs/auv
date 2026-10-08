"""The XL Catlin Seaview Survey's annotated photo-quadrats, as cover groups.

Each quadrat is a downward-facing photo of about a square metre; each of its
points was labelled by an expert with the survey's code for that region. A
quadrat here is its image (scaled to `pixels` across), its points in those
pixels, each point's group index (in the cover config's groups), and which
country and survey it came from, for splitting by country.
"""

from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass

import numpy as np


@dataclass
class Quadrat:
    id: str
    survey: str
    country: str
    image: np.ndarray          # (pixels, pixels, 3) uint8
    xy: np.ndarray             # (points, 2) float, column then row, in image pixels
    group: np.ndarray          # (points,) index into the cover groups
    random: np.ndarray         # (points,) whether the point was placed at random (a point count) or aimed


def group_of(label: str, function: str, rules: dict) -> str:
    if label in rules["by_code"]:
        return rules["by_code"][label]
    if label.endswith(rules.get("bleached_suffix", "-BL")):
        return "bleached_coral"
    if function in rules["by_function"]:
        return rules["by_function"][function]
    raise ValueError(f"no cover group for the survey's label {label!r} ({function})")


def load(root: pathlib.Path, cfg: dict, groups) -> list[Quadrat]:
    from PIL import Image

    d = cfg["data"]
    surveys = {r["surveyid"]: r for r in csv.DictReader(open(root / d["surveys"]))}
    points: dict[str, list] = {}
    for r in csv.DictReader(open(root / d["annotations"])):
        g = group_of(r["label"], r["func_group"], cfg["labels"])
        points.setdefault(r["quadratid"], []).append(
            (float(r["x"]) - 1, float(r["y"]) - 1, groups.names.index(g), r["method"] == "random"))
    out, n = [], int(d["pixels"])
    for qid, rows in sorted(points.items()):
        survey = qid[:5]
        image = Image.open(root / d["images"] / f"{qid}.jpg").convert("RGB")
        w, h = image.size
        a = np.array(rows, dtype=np.float64)
        xy = np.column_stack([(a[:, 0] + 0.5) * n / w - 0.5, (a[:, 1] + 0.5) * n / h - 0.5])
        out.append(Quadrat(qid, survey, surveys[survey]["country"], np.asarray(image.resize((n, n), Image.BILINEAR)),
                           xy.astype(np.float32), a[:, 2].astype(np.int64), a[:, 3].astype(bool)))
    return out


def split(quadrats: list[Quadrat], test: list[str], validation: list[str]) -> dict[str, list[Quadrat]]:
    parts = {"train": [], "validation": [], "test": []}
    for q in quadrats:
        parts["test" if q.country in test else "validation" if q.country in validation else "train"].append(q)
    seen = {k: {q.country for q in v} for k, v in parts.items()}
    if seen["train"] & (seen["test"] | seen["validation"]) or seen["test"] & seen["validation"]:
        raise ValueError(f"a country is in two parts: {seen}")
    return parts
