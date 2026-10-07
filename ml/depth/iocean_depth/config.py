"""Configs and where things live.

Configs are YAML in ml/depth/configs, in git. Data is not: the repository is
public and the data is gigabytes. It lives under one root, IOCEAN_ML_DATA
(in the container /data; on the box ~/iocean/ml/depth):

    datasets/<name>/    a dataset, built from configs/dataset/<name>.yaml
    runs/<run>/         a training run: its config, its commit, its history,
                        its checkpoint and its evaluation
"""

from __future__ import annotations

import os
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parents[1]
CONFIGS = HERE / "configs"


def data_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("IOCEAN_ML_DATA", pathlib.Path.home() / "iocean" / "ml" / "depth")).expanduser()


def load(path: str | pathlib.Path) -> dict:
    path = pathlib.Path(path)
    if not path.is_file() and (CONFIGS / path).is_file():
        path = CONFIGS / path
    return yaml.safe_load(path.read_text())


def dataset_dir(name: str) -> pathlib.Path:
    return data_root() / "datasets" / name


def runs_dir() -> pathlib.Path:
    return data_root() / "runs"
