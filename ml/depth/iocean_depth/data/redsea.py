"""Red Sea chips, found by ICESat-2: where its laser saw the seafloor, there is
shallow clear water, and in the Red Sea that is reef.

For each area in the dataset config (`red_sea.regions`): every ATL24 pass over
it, fetched into the shared cache (resumes; a pass fetched is not fetched
again), its seafloor photons inside the area, chip places laid over it as for
the lidar, and a chip wherever the photons fall in at least
`least_photon_cells` of its cells. The label is sparse (the cells the tracks
crossed); the region is "Red Sea" and the dataset `icesat-<area>`, so the
depth model is tested on them and never trained on them unless a config says.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import pathlib
import sys
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

import numpy as np

from . import chips, sentinel
from .build import STALLED, _done, _note_skip, _skipped


def photons(box, cache: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every ATL24 seafloor photon inside `box` (west, south, east north):
    longitude, latitude, orthometric height. Fetches what is not cached."""
    from iocean_places.fetch import icesat

    bearer = icesat.token()
    found = icesat.granules(box, bearer, most=10_000)
    lon, lat, height = [], [], []
    cache.mkdir(parents=True, exist_ok=True)
    print(f"  {len(found)} passes, {sum(g[2] for g in found) / 1024:.1f} GB", flush=True)
    for k, (name, url, _size, _when) in enumerate(found, 1):
        if not icesat.fetch(url, cache / name, bearer):
            continue
        got = icesat.seafloor(cache / name, box)
        if got is not None:
            lon.append(got[0]); lat.append(got[1]); height.append(got[2])
        if k % 20 == 0:
            print(f"  {k}/{len(found)} passes read", flush=True)
    if not lon:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(lon), np.concatenate(lat), np.concatenate(height).astype(float)


def _one_chip(cfg: dict, area: str, lat: float, lon: float, plon, plat, pheight):
    chip_id = f"red-sea-{area}-{lat:.4f}-{lon:.4f}"
    c, s2 = cfg["chip"], cfg["sentinel2"]
    try:
        grid = chips.chip_grid(lat, lon, c["cells"], c["cell_m"])
        y = chips.photons_label(grid, plon, plat, pheight)
        x, scenes = sentinel.stack(grid, scenes=s2["scenes"], covers=s2["covers_at_least"],
                                   bands=tuple(s2["bands"]), masked=tuple(s2["masked_scl"]),
                                   cloud=s2["cloud_below"], collection=s2["collection"])
        return chip_id, (x, y, {"region": "Red Sea", "dataset": f"icesat-{area}", "centre": [lat, lon],
                                "acrossM": grid.across, "cells": grid.cells, "bands": list(s2["bands"]),
                                "scenes": scenes, "label": "ICESat-2 ATL24 seafloor photons, the median of each cell's"})
    except Exception as bad:
        traceback.print_exc(limit=1, file=sys.stderr)
        return chip_id, f"error: {bad}"


def make_region_chips(cfg: dict, ds: pathlib.Path, cache: pathlib.Path, workers: int = 16, only: str | None = None) -> int:
    rs, c = cfg["red_sea"], cfg["chip"]
    across = c["cell_m"] * (c["cells"] - 1)
    (ds / "chips").mkdir(parents=True, exist_ok=True)
    done, skipped = _done(ds), _skipped(ds)
    for region in rs.get("regions", []):
        if only and region["name"] != only:
            continue
        box = tuple(region["bbox"])
        print(f"{region['name']}: {box}", flush=True)
        saved = ds / "icesat" / f"{region['name']}.npz"
        if saved.is_file():
            p = np.load(saved); plon, plat, ph = p["lon"], p["lat"], p["height"]
        else:
            plon, plat, ph = photons(box, cache)
            saved.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(saved, lon=plon, lat=plat, height=ph)
        keep = (ph < -0.5) & (ph > -40.0)
        plon, plat, ph = plon[keep], plat[keep], ph[keep]
        centres = chips.lattice([(None, box)], across)
        todo = []
        for lat, lon in centres:
            g = chips.chip_grid(lat, lon, c["cells"], c["cell_m"])
            west, south, east, north = g.bounds()
            inside = (plon >= west) & (plon <= east) & (plat >= south) & (plat <= north)
            if inside.sum() and np.isfinite(chips.photons_label(g, plon[inside], plat[inside], ph[inside])).sum() \
                    >= rs.get("least_photon_cells", 100):
                chip_id = f"red-sea-{region['name']}-{lat:.4f}-{lon:.4f}"
                if chip_id not in done | skipped:
                    todo.append((lat, lon, plon[inside], plat[inside], ph[inside]))
        print(f"{region['name']}: {len(plon):,} seafloor photons, {len(centres)} chip places, "
              f"{len(todo)} to make", flush=True)
        made = 0
        with ProcessPoolExecutor(workers, initializer=sentinel.use_gdal_env,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            pending = {pool.submit(_one_chip, cfg, region["name"], *t) for t in todo}
            while pending:
                finished, pending = wait(pending, timeout=STALLED, return_when=FIRST_COMPLETED)
                if not finished:
                    print(f"{region['name']}: no chip finished in {STALLED} s; stopping so the run can start again",
                          flush=True)
                    os._exit(3)
                for f in finished:
                    chip_id, result = f.result()
                    if isinstance(result, str):
                        _note_skip(ds, chip_id, result)
                        continue
                    x, y, record = result
                    chips.save(ds / "chips" / "red-sea", chip_id, x, y, "sparse", record,
                               c["shallowest_m"], c["deepest_m"])
                    made += 1
        print(f"{region['name']}: {made} chips made", flush=True)
        (ds / "icesat" / f"{region['name']}.json").write_text(json.dumps(
            {"region": region["name"], "bbox": list(box), "photons": int(len(plon)), "chipsMade": made}, indent=1))
    return 0
