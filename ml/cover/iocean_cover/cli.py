"""iocean-cover: coral cover from underwater imagery.

    iocean-cover fetch                       the model and its test set, at the pinned revisions
    iocean-cover check [--limit N]           the model on CoralscapesV2's test split -> checks/<name>/
    iocean-cover look  --tiles GLOB --at X,Y [--size M] [--res R,R]
                                             a patch of a mosaic and what the model says of it, to look at
    iocean-cover map   --tiles GLOB --name NAME [--res R]
                                             a cover map from a photo mosaic -> maps/<name>/
    iocean-cover video --video FILE[,FILE] --name NAME [--from S --to S] [--every S]
                       [--begin LAT,LON --end LAT,LON]
                                             cover along a video transect -> transects/<name>/
    iocean-cover colonies --video FILE[,FILE] --name NAME [--every S]
                                             every colony the videos show, cut out and sorted by type -> catalogs/<name>/
    iocean-cover finetune --config finetune/caribbean-v1.yaml [--run NAME]
                                             the model fine-tuned on labelled photo-quadrats -> runs/<run>/
    iocean-cover bands --name NAME --dem GLOB [--step M]
                                             a map's shares by depth, from the survey's elevation model

look, map and video take `--model RUN` to run a fine-tuned model (runs/<run>/model)
instead of the config's.

Data under IOCEAN_ML_DATA (see config.py). In the repository, `just ml-cover
...` runs these in the container on the box's second GPU.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import sys
import time

import yaml

from . import config


def _model(cfg: dict, run: str | None = None):
    from .classes import Groups
    from .segment import Segmenter

    if run:
        folder = config.data_root() / "runs" / run / "model"
        if not (folder / "config.json").is_file():
            raise SystemExit(f"no fine-tuned model in {folder}")
    else:
        folder = config.model_dir(cfg)
        if not (folder / "fetched.json").is_file():
            raise SystemExit(f"no model in {folder}; run `iocean-cover fetch` first")
    seg = Segmenter(folder, window=cfg["window"], stride=cfg["stride"])
    return seg, Groups(seg.id2label, cfg["groups"])


def _about(cfg: dict, run: str | None = None) -> dict:
    about = {"model": cfg["model"]["repo"], "revision": cfg["model"]["revision"], "licence": cfg["model"]["licence"],
             "cite": cfg["model"]["cite"], "config": cfg["name"], "commit": os.environ.get("GIT_COMMIT", "unknown")}
    if run:
        # A fine-tuned model carries its own check: the test countries it never saw.
        folder = config.data_root() / "runs" / run
        tuned = yaml.safe_load((folder / "config.yaml").read_text())
        r = json.loads((folder / "report.json").read_text())["fineTuned"]
        about.update({"model": f"{about['model']}, fine-tuned as {run}", "fineTuned": run,
                      "licence": tuned.get("licence", about["licence"]),
                      "checked": {"on": f"{r['quadrats']} photo-quadrats from countries it never saw",
                                  "meanAbsError": {k: v["dense"]["meanAbsError"] for k, v in r["groups"].items()},
                                  "bias": {k: v["dense"]["bias"] for k, v in r["groups"].items()},
                                  "report": f"runs/{run}/report.md"}})
        return about
    report = config.data_root() / "checks" / cfg["name"] / "report.json"
    if report.is_file():
        # How the model did on imagery it never saw, carried with what it
        # made: a place takes these as each share's error where the imagery is
        # like that, and must say otherwise where it is not.
        r = json.loads(report.read_text())
        about["checked"] = {
            "on": f"CoralscapesV2's test split, {r['frames']} frames from five Red Sea dive sites it never saw",
            "meanAbsError": {k: v["meanAbsError"] for k, v in r["cover"].items()},
            "bias": {k: v["bias"] for k, v in r["cover"].items()},
            "report": f"checks/{cfg['name']}/report.md"}
    return about


def _tiles(pattern: str) -> list[pathlib.Path]:
    paths = sorted(pathlib.Path(p) for p in glob.glob(os.path.expanduser(pattern)))
    if not paths:
        raise SystemExit(f"no tiles match {pattern}")
    return paths


def _fetch(cfg, a) -> int:
    from . import fetch

    print(fetch.model(cfg))
    print(fetch.test_set(cfg))
    print(fetch.outliner(cfg))
    return 0


def _check(cfg, a) -> int:
    from .evaluate import evaluate

    seg, groups = _model(cfg)
    out = config.data_root() / "checks" / (cfg["name"] + (f"-first-{a.limit}" if a.limit else ""))
    evaluate(seg, groups, config.test_dir(cfg), out, a.limit)
    (out / "about.json").write_text(json.dumps(_about(cfg), indent=1) + "\n")
    print((out / "report.md").read_text())
    return 0


def _look(cfg, a) -> int:
    import numpy as np
    import rasterio
    from PIL import Image

    from .mosaic import COLOURS, read

    seg, groups = _model(cfg, a.model)
    tiles = [rasterio.open(p) for p in _tiles(a.tiles)]
    x, y = (float(v) for v in a.at.split(","))
    out = config.data_root() / "looks"
    out.mkdir(parents=True, exist_ok=True)
    palette = np.array([COLOURS.get(n, (255, 255, 255)) for n in groups.names], np.uint8)
    from .segment import seabed_only, stretch

    allowed = seabed_only(groups, seg.id2label) if a.only_seabed else None
    for res in (float(r) for r in a.res.split(",")):
        n = int(round(a.size / res))
        rgb, seen = read(tiles, x - a.size / 2, y + a.size / 2, n, n, res)
        if a.stretch:
            rgb = stretch(rgb, seen)
        classes = seg.classes(rgb, allowed)
        shares = groups.shares(classes, seen)
        g = groups.of(classes)
        g[~seen] = groups.names.index("not_seabed")
        how = ("-seabed" if a.only_seabed else "") + ("-stretched" if a.stretch else "")
        name = out / f"{a.label or 'look'}-{x:.0f}-{y:.0f}-{a.size:g}m-{res * 1000:g}mm{how}.png"
        Image.fromarray(np.concatenate([rgb, palette[g]], 1)).save(name)
        top = np.bincount(classes[seen], minlength=len(seg.id2label)) / max(int(seen.sum()), 1)
        print(json.dumps({"png": str(name), "imaged": round(float(seen.mean()), 3),
                          "shares": {k: round(v, 3) for k, v in (shares or {}).items() if v >= 0.005},
                          "classes": {seg.id2label[i]: round(float(top[i]), 3) for i in np.argsort(-top)[:6] if top[i] >= 0.01}}))
    return 0


def _map(cfg, a) -> int:
    from .mosaic import make

    seg, groups = _model(cfg, a.model)
    settings = dict(cfg["mosaic"])
    if a.res:
        settings["metres_per_pixel"] = a.res
    about = _about(cfg, a.model)
    said = make(seg, groups, _tiles(a.tiles), config.data_root() / "maps" / a.name, settings, about)
    print(json.dumps({k: said[k] for k in ("imagedM2", "seabedM2", "shares", "seconds")}, indent=1))
    return 0


def _video(cfg, a) -> int:
    from .video import transect

    seg, groups = _model(cfg, a.model)
    point = (lambda v: tuple(float(x) for x in v.split(",")) if v else None)
    paths = [pathlib.Path(p) for p in a.video.split(",")]
    said = transect(seg, groups, paths, config.data_root() / "transects" / a.name, _about(cfg, a.model), every=a.every,
                    start=a.start, end=a.end, begin=point(a.begin), finish=point(a.finish))
    print(json.dumps({k: said[k] for k in ("frames", "framesUsed", "toSeconds", "lengthM", "cover", "seconds")},
                     indent=1))
    return 0


def _colonies(cfg, a) -> int:
    from .colonies import extract

    from .outline import Outliner

    seg, groups = _model(cfg, a.model)
    outliner = None
    if not a.no_outliner:
        o = cfg["outliner"]
        outliner = Outliner(config.outliner_dir(cfg), point_spacing=o["point_spacing"], min_score=o["min_score"],
                            min_purity=o["min_purity"], overlap=o["overlap"])
    said = extract(seg, groups, [pathlib.Path(p) for p in a.video.split(",")],
                   config.data_root() / "catalogs" / a.name, every=a.every, outliner=outliner)
    print(json.dumps({k: said[k] for k in ("frames", "colonies", "byClass", "seconds")}, indent=1))
    return 0


def _finetune(cfg, a) -> int:
    from .finetune import train

    tuned = config.load(a.tuning)
    run = config.data_root() / "runs" / (a.run or f"{tuned['name']}-{time.strftime('%Y%m%d-%H%M')}")
    info = train(tuned, cfg, config.model_dir(cfg), run, config.data_root())
    print(json.dumps({k: info[k] for k in ("run", "bestEpoch", "bestValidationMainError", "seconds")}, indent=1))
    print((run / "report.md").read_text())
    return 0


def _bands(cfg, a) -> int:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    folder = config.data_root() / "maps" / a.name
    with rasterio.open(folder / "cover.tif") as src:
        shares = src.read()
        names = list(src.descriptions)
        height = np.full(src.shape, np.nan, np.float32)
        for path in _tiles(a.dem):
            with rasterio.open(path) as dem:
                part = np.full(src.shape, np.nan, np.float32)
                reproject(rasterio.band(dem, 1), part, src_nodata=dem.nodata, dst_nodata=np.nan,
                          dst_transform=src.transform, dst_crs=src.crs, resampling=Resampling.average)
                height = np.where(np.isfinite(part), part, height)
    seabed = shares[names.index("seabed")]
    cell = json.loads((folder / "cover.json").read_text())["cellM"]
    depth = -height
    rows = []
    for lo in np.arange(np.floor(np.nanmin(depth)), np.nanmax(depth), a.step):
        here = (depth >= lo) & (depth < lo + a.step) & (seabed > 0)
        if here.sum() < 100:
            continue
        w = seabed[here]
        row = {"depthM": f"{lo:g}-{lo + a.step:g}", "seabedM2": round(float(w.sum()) * cell * cell, 1)}
        for k, name in enumerate(names[:-1]):
            row[name] = round(float(np.nansum(shares[k][here] * w) / w.sum()), 4)
        rows.append(row)
    said = {"map": a.name, "dem": a.dem, "heightsAre": "the survey's own datum (SQUID-5 at Looe Key: NAVD88)", "bands": rows}
    (folder / "bands.json").write_text(json.dumps(said, indent=1) + "\n")
    keep = [n for n in names[:-1] if max(r[n] for r in rows) >= 0.02]
    print("depth m   seabed m2  " + "  ".join(f"{n:>14}" for n in keep))
    for r in rows:
        print(f"{r['depthM']:<9} {r['seabedM2']:>9}  " + "  ".join(f"{r[n]:>14.1%}" for n in keep))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iocean-cover", description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="cover.yaml")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch")
    c = sub.add_parser("check")
    c.add_argument("--limit", type=int, help="only the first N frames")
    lk = sub.add_parser("look")
    lk.add_argument("--tiles", required=True)
    lk.add_argument("--at", required=True, help="centre, in the tiles' coordinates: X,Y")
    lk.add_argument("--size", type=float, default=10.0, help="metres across")
    lk.add_argument("--res", default="0.005,0.01", help="metres a pixel, one or more")
    lk.add_argument("--label")
    lk.add_argument("--model", help="a fine-tuned run instead of the config's model")
    lk.add_argument("--only-seabed", action="store_true", help="rule out the classes that are not seabed")
    lk.add_argument("--stretch", action="store_true", help="stretch each channel's contrast first")
    m = sub.add_parser("map")
    m.add_argument("--tiles", required=True)
    m.add_argument("--name", required=True)
    m.add_argument("--res", type=float, help="metres a pixel (the config's by default)")
    m.add_argument("--model", help="a fine-tuned run instead of the config's model")
    v = sub.add_parser("video")
    v.add_argument("--video", required=True, help="one file, or several a transect was cut into, comma separated")
    v.add_argument("--name", required=True)
    v.add_argument("--from", dest="start", type=float, default=0.0, help="seconds: where the transect begins")
    v.add_argument("--to", dest="end", type=float, help="seconds: where it ends")
    v.add_argument("--every", type=float, default=1.0, help="seconds between the frames read")
    v.add_argument("--begin", help="the transect's start: LAT,LON")
    v.add_argument("--end", dest="finish", help="the transect's end: LAT,LON")
    v.add_argument("--model", help="a fine-tuned run instead of the config's model")
    co = sub.add_parser("colonies")
    co.add_argument("--video", required=True, help="videos, comma separated; each is read on its own")
    co.add_argument("--name", required=True)
    co.add_argument("--every", type=float, default=1.0, help="seconds between the frames read")
    co.add_argument("--model", help="a fine-tuned run instead of the config's model")
    co.add_argument("--no-outliner", action="store_true", help="connected patches of a class instead of SAM 2's outlines")
    f = sub.add_parser("finetune")
    f.add_argument("--config", dest="tuning", required=True, help="finetune/<name>.yaml")
    f.add_argument("--run")
    b = sub.add_parser("bands")
    b.add_argument("--name", required=True)
    b.add_argument("--dem", required=True, help="the survey's elevation model tiles, heights in metres")
    b.add_argument("--step", type=float, default=2.0)
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    return {"fetch": _fetch, "check": _check, "look": _look, "map": _map, "video": _video, "colonies": _colonies, "finetune": _finetune, "bands": _bands}[a.command](cfg, a)


if __name__ == "__main__":
    sys.exit(main())
