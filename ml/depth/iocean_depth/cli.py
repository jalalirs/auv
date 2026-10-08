"""iocean-depth: build a dataset, train, evaluate.

    iocean-depth dataset build   --config dataset/depth-v1.yaml [--step lidar|chips|red-sea|red-sea-regions|all]
    iocean-depth dataset summary --config dataset/depth-v1.yaml
    iocean-depth dataset manifest --config dataset/depth-v1.yaml
    iocean-depth train    --config train/unet-v1.yaml [--run NAME]
    iocean-depth evaluate --run RUN
    iocean-depth runs

Data under IOCEAN_ML_DATA (see config.py). In the repository, `just ml-depth
...` runs these in the container on the box's second GPU.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

from . import config


def _dataset(a) -> int:
    from .data import build

    cfg = config.load(a.config)
    ds = config.dataset_dir(cfg["name"])
    ds.mkdir(parents=True, exist_ok=True)
    if a.action == "summary":
        print(json.dumps(build.summary(ds), indent=1))
        return 0
    if a.action == "manifest":
        path = pathlib.Path(a.config) if pathlib.Path(a.config).is_file() else config.CONFIGS / a.config
        manifest = build.write_manifest(cfg, ds, path)
        print(json.dumps({k: manifest[k] for k in ("name", "chips", "labelledCells", "skipped")}, indent=1))
        return 0
    if a.action == "chips-once":
        return build.make_chips(cfg, ds, a.only, a.workers)
    if a.action == "regions-once":
        from .data import redsea
        return redsea.make_region_chips(cfg, ds, pathlib.Path(a.icesat_cache), min(a.workers, 16), a.only)
    steps = ("lidar", "chips", "red-sea", "red-sea-regions") if a.step == "all" else (a.step,)
    if "lidar" in steps:
        build.fetch_lidar(cfg, ds, a.only)
    if "chips" in steps:
        if _again_until_done("chips-once", a) != 0:
            return 1
    if "red-sea" in steps:
        build.red_sea(cfg, ds, pathlib.Path(a.reference).expanduser())
    if "red-sea-regions" in steps and _again_until_done("regions-once", a) != 0:
        return 1
    manifest = build.write_manifest(cfg, ds, config.CONFIGS / a.config if not pathlib.Path(a.config).is_file()
                                    else pathlib.Path(a.config))
    print(json.dumps({k: manifest[k] for k in ("name", "chips", "labelledCells", "skipped")}, indent=1))
    return 0


def _again_until_done(action: str, a) -> int:
    """Run a step in its own process until it finishes: one that makes no chip
    for a while exits 3, and the next resumes where it stopped."""
    for attempt in range(1, a.attempts + 1):
        print(f"== {action}, attempt {attempt}", flush=True)
        done = subprocess.call([sys.executable, "-m", "iocean_depth.cli", "dataset", action, "--config", str(a.config),
                                "--workers", str(a.workers), "--icesat-cache", a.icesat_cache]
                               + (["--only", a.only] if a.only else []))
        if done == 0:
            return 0
    print(f"{action}: gave up after every attempt stalled", file=sys.stderr)
    return 1


def _train(a) -> int:
    from .evaluate import evaluate
    from .train import train

    cfg = config.load(a.config)
    run = config.runs_dir() / (a.run or f"{cfg['name']}-{time.strftime('%Y%m%d-%H%M')}")
    ds = config.dataset_dir(cfg["dataset"])
    info = train(cfg, run, ds)
    print(json.dumps({k: info[k] for k in ("run", "bestEpoch", "bestValidationRmsM", "seconds")}, indent=1))
    if not a.no_evaluate:
        evaluate(run, ds)
        print((run / "report.md").read_text())
    return 0


def _evaluate(a) -> int:
    from .evaluate import evaluate

    run = config.runs_dir() / a.run
    cfg = config.load(run / "config.yaml")
    evaluate(run, config.dataset_dir(cfg["dataset"]))
    print((run / "report.md").read_text())
    return 0


def _runs(a) -> int:
    for run in sorted(config.runs_dir().glob("*")):
        info = json.loads((run / "run.json").read_text()) if (run / "run.json").is_file() else {}
        report = json.loads((run / "report.json").read_text()) if (run / "report.json").is_file() else {}
        held = report.get("held-out", {})
        every = held.get("all") or next(iter(held.values()), {})
        print(f"{run.name:<40} best epoch {info.get('bestEpoch', '?'):>3}  "
              f"held-out rms {every.get('unet', {}).get('rmsM', '?')} (linear {every.get('linearBaseline', {}).get('rmsM', '?')})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iocean-depth", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    d = sub.add_parser("dataset")
    d.add_argument("action", choices=("build", "summary", "manifest", "chips-once", "regions-once"))
    d.add_argument("--config", default="dataset/depth-v1.yaml")
    d.add_argument("--step", default="all", choices=("all", "lidar", "chips", "red-sea", "red-sea-regions"))
    d.add_argument("--icesat-cache", default="/icesat", help="where ICESat-2 passes are kept once fetched")
    d.add_argument("--only", help="one survey, by its slug")
    d.add_argument("--workers", type=int, default=32)
    d.add_argument("--attempts", type=int, default=30)
    d.add_argument("--reference", default="/reference", help="the places' reference folders (the Red Sea)")
    t = sub.add_parser("train")
    t.add_argument("--config", default="train/unet-v1.yaml")
    t.add_argument("--run", help="the run's name; by default the config's name and the time")
    t.add_argument("--no-evaluate", action="store_true")
    e = sub.add_parser("evaluate")
    e.add_argument("--run", required=True)
    sub.add_parser("runs")
    a = ap.parse_args(argv)
    if a.command == "dataset":
        return _dataset(a)
    return {"train": _train, "evaluate": _evaluate, "runs": _runs}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
