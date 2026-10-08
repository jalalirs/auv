"""Configs and where things live.

Configs are YAML in ml/cover/configs, in git. Data is not: it lives under one
root, IOCEAN_ML_DATA (in the container /data; on the box ~/iocean/ml/cover):

    models/<repo>/<revision>/     a model as fetched, with fetched.json
    datasets/<repo>/<revision>/   a test set as fetched
    checks/<name>/                a check of a model: report.json, report.md
    maps/<name>/                  a cover map made from a photo mosaic
"""

from __future__ import annotations

import os
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parents[1]
CONFIGS = HERE / "configs"


def data_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("IOCEAN_ML_DATA", pathlib.Path.home() / "iocean" / "ml" / "cover")).expanduser()


def load(path: str | pathlib.Path = "cover.yaml") -> dict:
    path = pathlib.Path(path)
    if not path.is_file() and (CONFIGS / path).is_file():
        path = CONFIGS / path
    return yaml.safe_load(path.read_text())


def model_dir(cfg: dict) -> pathlib.Path:
    return data_root() / "models" / cfg["model"]["repo"].replace("/", "--") / cfg["model"]["revision"][:12]


def test_dir(cfg: dict) -> pathlib.Path:
    return data_root() / "datasets" / cfg["test"]["repo"].replace("/", "--") / cfg["test"]["revision"][:12]
