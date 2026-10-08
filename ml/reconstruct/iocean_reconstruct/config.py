"""Configs and where things live.

Configs are YAML in ml/reconstruct/configs, in git. Data is not: it lives under
IOCEAN_ML_DATA (in the container /data; on the box ~/iocean/ml/reconstruct):

    runs/<name>/frames/      the video's frames, as read
    runs/<name>/colmap/      COLMAP's database, sparse model and dense workspace
    runs/<name>/patch/       the reef patch: mesh (PLY and USD), DEM and orthophoto
                             in its own metres, and patch.json saying how it was made
"""

from __future__ import annotations

import os
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parents[1]
CONFIGS = HERE / "configs"


def data_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("IOCEAN_ML_DATA", pathlib.Path.home() / "iocean" / "ml" / "reconstruct")).expanduser()


def load(path: str | pathlib.Path = "default.yaml") -> dict:
    path = pathlib.Path(path)
    if not path.is_file() and (CONFIGS / path).is_file():
        path = CONFIGS / path
    return yaml.safe_load(path.read_text())


def run_dir(name: str) -> pathlib.Path:
    return data_root() / "runs" / name
