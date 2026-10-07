"""Make the depth model's training set.

    tools/training-set lidar                 fetch the lidar datasets (lidar_sources.json)
    tools/training-set chips [--only SLUG]   cut them into chips, with Sentinel-2 over each
    tools/training-set red-sea               chips over the Red Sea places, ICESat-2 labelled
    tools/training-set summary               what there is

Everything goes under --root (default ~/iocean/training/depth-v1): lidar/
for the surveys as fetched, chips/ for the .npz chips and chips/index.jsonl.
Each step resumes: a dataset fetched whole is not fetched again, and a chip in
the index is not made again.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import traceback

import numpy as np

from . import chips, lidar, sentinel

ROOT = pathlib.Path.home() / "iocean" / "training" / "depth-v1"
_lock = threading.Lock()


def _done(root: pathlib.Path) -> set[str]:
    index = root / "chips" / "index.jsonl"
    if not index.is_file():
        return set()
    return {json.loads(line)["chip"] for line in index.read_text().splitlines() if line.strip()}


def _skipped(root: pathlib.Path) -> set[str]:
    path = root / "chips" / "skipped.jsonl"
    return {json.loads(line)["chip"] for line in path.read_text().splitlines()} if path.is_file() else set()


def _note_skip(root: pathlib.Path, chip_id: str, why: str) -> None:
    with _lock, open(root / "chips" / "skipped.jsonl", "a") as out:
        out.write(json.dumps({"chip": chip_id, "why": why}) + "\n")


def fetch_lidar(root: pathlib.Path, only: str | None) -> None:
    for d in lidar.datasets():
        if only and d["slug"] != only:
            continue
        print(f"{d['slug']}: {d['gb']} GB, {d['files']} files", flush=True)
        lidar.fetch(d["slug"], root / "lidar")


def _one_chip(root: str, d: dict, tiles: list, lat: float, lon: float):
    """One chip, in a worker process: (id, why it was skipped) or (id, (x, y, record))."""
    chip_id = f"{d['slug']}-{lat:.4f}-{lon:.4f}"
    try:
        grid = chips.chip_grid(lat, lon)
        y = chips.lidar_label(grid, tiles)
        if chips.labelled_share(y) < chips.LABELLED_AT_LEAST:
            return chip_id, f"labelled {chips.labelled_share(y):.2f}"
        x, scenes = sentinel.stack(grid)
        return chip_id, (x, y, {"region": d["region"], "dataset": d["slug"], "surveyYear": d["year"],
                                "centre": [lat, lon], "acrossM": chips.ACROSS, "cells": chips.CELLS,
                                "bands": list(sentinel.BANDS), "scenes": scenes,
                                "label": f"NOAA topobathy lidar ({d['name']}, {d['year']}), averaged into 10 m cells"})
    except Exception as bad:   # one chip is not the set: say why and go on
        traceback.print_exc(limit=1, file=sys.stderr)
        return chip_id, f"error: {bad}"


def make_chips(root: pathlib.Path, only: str | None, workers: int, most: int | None) -> None:
    (root / "chips").mkdir(parents=True, exist_ok=True)
    done, skipped = _done(root), _skipped(root)
    for d in lidar.datasets():
        if only and d["slug"] != only:
            continue
        folder = root / "lidar" / d["slug"]
        tifs = sorted(folder.glob("*.tif"))
        if not tifs:
            print(f"{d['slug']}: not fetched; run `lidar` first", flush=True)
            continue
        tiles = lidar.footprints(tifs)
        centres = chips.lattice(tiles)
        # Only where the survey measured enough water a satellite can see into.
        lon, lat, area = lidar.wet(tiles)
        chip_area = chips.ACROSS ** 2
        kept = []
        for c_lat, c_lon in centres:
            g = chips.chip_grid(c_lat, c_lon)
            west, south, east, north = g.bounds()
            n = int(((lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)).sum())
            if n * area >= 0.8 * chips.LABELLED_AT_LEAST * chip_area:
                kept.append((c_lat, c_lon))
        print(f"{d['slug']}: {len(kept)} of {len(centres)} chip places have water the survey measured", flush=True)
        centres = kept
        if most:
            centres = centres[:most]
        todo = [(lat, lon) for lat, lon in centres
                if f"{d['slug']}-{lat:.4f}-{lon:.4f}" not in done | skipped]
        print(f"{d['slug']}: {len(tiles)} tiles, {len(centres)} chip places, {len(todo)} to make", flush=True)

        made = 0
        # Processes, not threads: GDAL in one process across many threads
        # deadlocked. Each chip is made in a worker; only the parent writes
        # the index, so nothing is written twice at once.
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(workers, initializer=sentinel.use_gdal_env) as pool:
            futures = [pool.submit(_one_chip, str(root), d, tiles, lat, lon) for lat, lon in todo]
            for k, f in enumerate(futures, 1):
                chip_id, result = f.result()
                if isinstance(result, str):
                    _note_skip(root, chip_id, result)
                else:
                    x, y, record = result
                    chips.save(root / "chips" / d["region"].replace(" ", "-").replace("/", "-").lower(),
                               chip_id, x, y, "dense", record)
                    made += 1
                if k % 25 == 0:
                    print(f"  {d['slug']}: {k}/{len(todo)} looked at, {made} made", flush=True)
        print(f"{d['slug']}: {made} chips made", flush=True)


# The Red Sea places, labelled by ICESat-2 alone: (place, reference folder name).
RED_SEA = (("shushah", "shushah"), ("al-fahal", "al-fahal"))


def red_sea(root: pathlib.Path, reference: pathlib.Path) -> None:
    (root / "chips").mkdir(parents=True, exist_ok=True)
    done = _done(root)
    from ..grid import metres_per_degree
    for place, folder in RED_SEA:
        ref = reference / folder
        said = json.loads((ref / f"{folder}.json").read_text())
        lat0, lon0 = said["centre"]["latitude"], said["centre"]["longitude"]
        across = float(said["acrossMetres"])
        points = np.load(ref / "icesat_depths.npy")
        east, north = metres_per_degree(lat0)
        lon, lat = lon0 + points[:, 0] / east, lat0 + points[:, 1] / north
        n = max(1, int(round(across / chips.ACROSS)))
        for i in range(n):
            for j in range(n):
                y0 = -across / 2 + (i + 0.5) * across / n
                x0 = -across / 2 + (j + 0.5) * across / n
                clat, clon = lat0 + y0 / north, lon0 + x0 / east
                chip_id = f"red-sea-{place}-{clat:.4f}-{clon:.4f}"
                if chip_id in done:
                    continue
                grid = chips.chip_grid(clat, clon)
                y = chips.photons_label(grid, lon, lat, points[:, 2].astype(float))
                if np.isfinite(y).sum() < 50:
                    continue
                x, scenes = sentinel.stack(grid)
                r = chips.save(root / "chips" / "red-sea", chip_id, x, y, "sparse",
                               {"region": "Red Sea", "dataset": place, "centre": [clat, clon], "acrossM": chips.ACROSS,
                                "cells": chips.CELLS, "bands": list(sentinel.BANDS), "scenes": scenes,
                                "label": "ICESat-2 ATL24 seafloor photons, the median of each cell's"})
                print(f"  {chip_id}: {int(np.isfinite(y).sum())} labelled cells", flush=True)


def summary(root: pathlib.Path) -> dict:
    index = root / "chips" / "index.jsonl"
    rows = [json.loads(line) for line in index.read_text().splitlines()] if index.is_file() else []
    by_region: dict[str, dict] = {}
    for r in rows:
        one = by_region.setdefault(r["region"], {"chips": 0, "labelledCells": 0, "kind": r["labelKind"]})
        one["chips"] += 1
        one["labelledCells"] += int(round(r["labelledShare"] * chips.CELLS * chips.CELLS))
    out = {"chips": len(rows), "byRegion": by_region,
           "labelledCells": sum(v["labelledCells"] for v in by_region.values()),
           "skipped": len(_skipped(root))}
    print(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="training-set", description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=("lidar", "chips", "red-sea", "summary"))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--only", help="one dataset, by its slug")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--most", type=int, help="at most this many chip places per dataset (a trial run)")
    ap.add_argument("--reference", default=str(pathlib.Path.home() / "iocean" / "reference"))
    asked = ap.parse_args(argv)
    root = pathlib.Path(asked.root).expanduser()
    if asked.step == "lidar":
        fetch_lidar(root, asked.only)
    elif asked.step == "chips":
        make_chips(root, asked.only, asked.workers, asked.most)
    elif asked.step == "red-sea":
        red_sea(root, pathlib.Path(asked.reference).expanduser())
    else:
        summary(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
