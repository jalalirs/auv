"""Fetch the model and its test set, at the revisions the config pins.

Both come from Hugging Face. What was fetched, from where and when is written
beside it (fetched.json), so a map made later can say which bytes made it.
"""

from __future__ import annotations

import json
import time

from . import config


def _fetched(folder, repo: str, revision: str, kind: str, licence: str | None) -> None:
    (folder / "fetched.json").write_text(json.dumps({
        "repo": repo, "kind": kind, "revision": revision, "licence": licence,
        "url": f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{repo}",
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1) + "\n")


def model(cfg: dict) -> str:
    from huggingface_hub import snapshot_download

    m = cfg["model"]
    folder = config.model_dir(cfg)
    if not (folder / "fetched.json").is_file():
        snapshot_download(m["repo"], revision=m["revision"], local_dir=folder,
                          allow_patterns=["config.json", "preprocessor_config.json", "model.safetensors", "README.md"])
        _fetched(folder, m["repo"], m["revision"], "model", m.get("licence"))
    return str(folder)


def test_set(cfg: dict) -> str:
    from huggingface_hub import hf_hub_download

    t = cfg["test"]
    folder = config.test_dir(cfg)
    if not (folder / "fetched.json").is_file():
        for name in t["files"] + ["id2label.json"]:
            hf_hub_download(t["repo"], name, repo_type="dataset", revision=t["revision"], local_dir=folder)
        _fetched(folder, t["repo"], t["revision"], "dataset", "Apache-2.0")
    return str(folder)


def outliner(cfg: dict) -> str:
    from huggingface_hub import hf_hub_download

    o = cfg["outliner"]
    folder = config.outliner_dir(cfg)
    if not (folder / "fetched.json").is_file():
        for name in o["files"]:
            hf_hub_download(o["repo"], name, revision=o["revision"], local_dir=folder)
        _fetched(folder, o["repo"], o["revision"], "model", o.get("licence"))
    return str(folder)
