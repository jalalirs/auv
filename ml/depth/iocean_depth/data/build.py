"""Build a depth dataset from its config: the lidar, the chips, the Red Sea.

A dataset lives in one folder (`datasets/<name>/` under the data root):

    lidar/<survey>/          the surveys as fetched
    chips/<region>/*.npz     one chip each: x (bands), y (heights), kind
    chips/index.jsonl        where each chip is, its region, its label, its scenes
    chips/skipped.jsonl      chip places refused, and why
    manifest.json            what was built, from which config, by which commit

Every step resumes: a survey fetched whole is not fetched again, a chip in the
index or the skipped list is not made again.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import traceback

import numpy as np

from . import chips, lidar, sentinel

# A chip that takes longer than this is given up on; a run that makes no chip
# for STALLED seconds stops, and the loop around it starts it again (it resumes).
CHIP_SECONDS = 240
STALLED = 240


def _done(ds: pathlib.Path) -> set[str]:
    index = ds / "chips" / "index.jsonl"
    return {json.loads(line)["chip"] for line in index.read_text().splitlines() if line.strip()} if index.is_file() else set()


def _skipped(ds: pathlib.Path) -> set[str]:
    path = ds / "chips" / "skipped.jsonl"
    return {json.loads(line)["chip"] for line in path.read_text().splitlines() if line.strip()} if path.is_file() else set()


def _note_skip(ds: pathlib.Path, chip_id: str, why: str) -> None:
    with open(ds / "chips" / "skipped.jsonl", "a") as out:
        out.write(json.dumps({"chip": chip_id, "why": why}) + "\n")


def _region_folder(region: str) -> str:
    return region.replace(" ", "-").replace("/", "-").lower()


def fetch_lidar(cfg: dict, ds: pathlib.Path, only: str | None = None) -> None:
    for d in cfg["lidar"]:
        if only and d["slug"] != only:
            continue
        print(f"{d['slug']}: {d['gb']} GB, {d['files']} files", flush=True)
        lidar.fetch(d["slug"], ds / "lidar")


def _one_chip(cfg: dict, d: dict, tiles: list, lat: float, lon: float):
    """One chip, in a worker process: (id, why it was skipped) or (id, (x, y, record))."""
    import signal

    chip_id = f"{d['slug']}-{lat:.4f}-{lon:.4f}"
    c, s2 = cfg["chip"], cfg["sentinel2"]

    def gave_up(*_):
        raise TimeoutError(f"no chip in {CHIP_SECONDS} s")

    signal.signal(signal.SIGALRM, gave_up)
    signal.alarm(CHIP_SECONDS)
    try:
        grid = chips.chip_grid(lat, lon, c["cells"], c["cell_m"])
        y = chips.lidar_label(grid, tiles)
        share = chips.labelled_share(y, c["shallowest_m"], c["deepest_m"])
        if share < c["labelled_at_least"]:
            return chip_id, f"labelled {share:.2f}"
        x, scenes = sentinel.stack(grid, scenes=s2["scenes"], covers=s2["covers_at_least"],
                                   bands=tuple(s2["bands"]), masked=tuple(s2["masked_scl"]),
                                   cloud=s2["cloud_below"], collection=s2["collection"])
        return chip_id, (x, y, {"region": d["region"], "dataset": d["slug"], "surveyYear": d["year"],
                                "centre": [lat, lon], "acrossM": grid.across, "cells": grid.cells,
                                "bands": list(s2["bands"]), "scenes": scenes,
                                "label": f"NOAA topobathy lidar ({d['name']}, {d['year']}), averaged into "
                                         f"{c['cell_m']:g} m cells"})
    except Exception as bad:   # one chip is not the set: say why and go on
        traceback.print_exc(limit=1, file=sys.stderr)
        return chip_id, f"error: {bad}"
    finally:
        signal.alarm(0)


def make_chips(cfg: dict, ds: pathlib.Path, only: str | None = None, workers: int = 32, most: int | None = None) -> int:
    """Chips over every survey; returns 3 if it stopped because nothing was
    finishing (the caller starts it again), 0 when every survey is done."""
    import multiprocessing
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

    c = cfg["chip"]
    across = c["cell_m"] * (c["cells"] - 1)
    (ds / "chips").mkdir(parents=True, exist_ok=True)
    done, skipped = _done(ds), _skipped(ds)
    for d in cfg["lidar"]:
        if only and d["slug"] != only:
            continue
        tifs = sorted((ds / "lidar" / d["slug"]).glob("*.tif"))
        if not tifs:
            print(f"{d['slug']}: not fetched; fetch the lidar first", flush=True)
            continue
        tiles = lidar.footprints(tifs)
        centres = chips.lattice(tiles, across)
        # Only where the survey measured enough water a satellite can see into.
        lon, lat, area = lidar.wet(tiles, shallowest=c["shallowest_m"], deepest=c["deepest_m"])
        kept = []
        for c_lat, c_lon in centres:
            west, south, east, north = chips.chip_grid(c_lat, c_lon, c["cells"], c["cell_m"]).bounds()
            n = int(((lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)).sum())
            if n * area >= 0.8 * c["labelled_at_least"] * across ** 2:
                kept.append((c_lat, c_lon))
        if most:
            kept = kept[:most]
        todo = [(a, b) for a, b in kept if f"{d['slug']}-{a:.4f}-{b:.4f}" not in done | skipped]
        print(f"{d['slug']}: {len(tiles)} tiles, {len(kept)} of {len(centres)} chip places have water the "
              f"survey measured, {len(todo)} to make", flush=True)
        made, k = 0, 0
        # Spawned, not forked: the parent has used GDAL by now, and a forked
        # child can inherit a lock one of its threads held at the fork and
        # wait on it for ever, deep in C where no alarm reaches.
        with ProcessPoolExecutor(workers, initializer=sentinel.use_gdal_env,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            pending = {pool.submit(_one_chip, cfg, d, tiles, a, b) for a, b in todo}
            while pending:
                finished, pending = wait(pending, timeout=STALLED, return_when=FIRST_COMPLETED)
                if not finished:
                    print(f"{d['slug']}: no chip finished in {STALLED} s; stopping so the run can start again",
                          flush=True)
                    os._exit(3)
                for f in finished:
                    k += 1
                    chip_id, result = f.result()
                    if isinstance(result, str):
                        _note_skip(ds, chip_id, result)
                    else:
                        x, y, record = result
                        chips.save(ds / "chips" / _region_folder(d["region"]), chip_id, x, y, "dense", record,
                                   c["shallowest_m"], c["deepest_m"])
                        made += 1
                    if k % 25 == 0:
                        print(f"  {d['slug']}: {k}/{len(todo)} looked at, {made} made", flush=True)
        print(f"{d['slug']}: {made} chips made", flush=True)
    return 0


def red_sea(cfg: dict, ds: pathlib.Path, reference: pathlib.Path) -> None:
    """Chips over the Red Sea places, labelled by the ICESat-2 photons in
    their reference folders: the test of how the model does on Red Sea water."""
    from iocean_places.grid import metres_per_degree

    c, s2 = cfg["chip"], cfg["sentinel2"]
    across = c["cell_m"] * (c["cells"] - 1)
    (ds / "chips").mkdir(parents=True, exist_ok=True)
    done = _done(ds)
    for place in cfg["red_sea"]["places"]:
        ref = reference / place
        said = json.loads((ref / f"{place}.json").read_text())
        lat0, lon0 = said["centre"]["latitude"], said["centre"]["longitude"]
        size = float(said["acrossMetres"])
        points = np.load(ref / "icesat_depths.npy")
        east, north = metres_per_degree(lat0)
        lon, lat = lon0 + points[:, 0] / east, lat0 + points[:, 1] / north
        n = max(1, int(round(size / across)))
        for i in range(n):
            for j in range(n):
                clat = lat0 + (-size / 2 + (i + 0.5) * size / n) / north
                clon = lon0 + (-size / 2 + (j + 0.5) * size / n) / east
                chip_id = f"red-sea-{place}-{clat:.4f}-{clon:.4f}"
                if chip_id in done:
                    continue
                grid = chips.chip_grid(clat, clon, c["cells"], c["cell_m"])
                y = chips.photons_label(grid, lon, lat, points[:, 2].astype(float))
                if np.isfinite(y).sum() < 50:
                    continue
                x, scenes = sentinel.stack(grid, scenes=s2["scenes"], covers=s2["covers_at_least"],
                                           bands=tuple(s2["bands"]), masked=tuple(s2["masked_scl"]),
                                           cloud=s2["cloud_below"], collection=s2["collection"])
                chips.save(ds / "chips" / "red-sea", chip_id, x, y, "sparse",
                           {"region": "Red Sea", "dataset": place, "centre": [clat, clon], "acrossM": grid.across,
                            "cells": grid.cells, "bands": list(s2["bands"]), "scenes": scenes,
                            "label": "ICESat-2 ATL24 seafloor photons, the median of each cell's"},
                           c["shallowest_m"], c["deepest_m"])
                print(f"  {chip_id}: {int(np.isfinite(y).sum())} labelled cells", flush=True)


def summary(ds: pathlib.Path) -> dict:
    index = ds / "chips" / "index.jsonl"
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()] if index.is_file() else []
    by_region: dict[str, dict] = {}
    for r in rows:
        one = by_region.setdefault(r["region"], {"chips": 0, "labelledCells": 0, "datasets": set(),
                                                 "label": r["labelKind"]})
        one["chips"] += 1
        one["datasets"].add(r["dataset"])
        one["labelledCells"] += int(round(r["labelledShare"] * r["cells"] * r["cells"]))
    for one in by_region.values():
        one["datasets"] = sorted(one["datasets"])
    skipped = [json.loads(line) for line in (ds / "chips" / "skipped.jsonl").read_text().splitlines()
               if line.strip()] if (ds / "chips" / "skipped.jsonl").is_file() else []
    return {"chips": len(rows), "labelledCells": sum(v["labelledCells"] for v in by_region.values()),
            "byRegion": by_region,
            "skipped": {"tooLittleWater": sum(not s["why"].startswith("error") for s in skipped),
                        "errors": sum(s["why"].startswith("error") for s in skipped)}}


def write_manifest(cfg: dict, ds: pathlib.Path, config_path: pathlib.Path) -> dict:
    """What this dataset is, said once beside it: the config it was built from,
    the commit, when, and what came out."""
    manifest = {"name": cfg["name"], "config": str(config_path), "configText": config_path.read_text(),
                "commit": os.environ.get("GIT_COMMIT", "unknown"),
                "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **summary(ds)}
    (ds / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest
