"""The inputs: what Sentinel-2 saw over a chip, band by band.

Not the true-colour picture the places use (8-bit, three bands, already
stretched), but surface reflectance in the bands that see into water and the
ones that say what is not water: coastal blue, blue, green, red, the first red
edge, near infrared and the first shortwave infrared. Each band is the median
of up to `scenes` clear scenes, cloud and cloud shadow masked out per scene by
the scene's own classification (SCL), all on the chip's 10 m grid.
"""

from __future__ import annotations

import json
import urllib.request

import numpy as np

from ..grid import Grid
from ..sources.raster import onto

SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-c1-l2a"
BANDS = ("coastal", "blue", "green", "red", "rededge1", "nir", "swir16")
# SCL: 3 cloud shadow, 8 and 9 cloud, 10 thin cirrus. Water (6) and the rest are kept.
MASKED = (3, 8, 9, 10)


def clear_scenes(grid: Grid, cloud: float = 20.0, most: int = 40, since: str = "2017-01-01T00:00:00Z",
                 until: str = "2030-01-01T00:00:00Z") -> list[dict]:
    asking = json.dumps({"collections": [COLLECTION], "bbox": list(grid.bounds()),
                         "datetime": f"{since}/{until}", "query": {"eo:cloud_cover": {"lt": cloud}},
                         "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
                         "limit": most}).encode()
    request = urllib.request.Request(SEARCH, data=asking, headers={"content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as answer:
                return json.loads(answer.read()).get("features", [])
        except OSError:
            if attempt == 3:
                raise
            import time
            time.sleep(5 * (attempt + 1))
    return []


def _scale(asset: dict) -> tuple[float, float]:
    band = (asset.get("raster:bands") or [{}])[0]
    return float(band.get("scale", 1e-4)), float(band.get("offset", 0.0))


# How GDAL reads a cloud-optimised GeoTIFF over HTTP without the overhead:
# no directory listing beside each file, ranges merged, HTTP/2, a cache. A
# scene's eight reads went from 29 s to 9 s with these, and its bands are read
# side by side.
# Set once, in the process's environment, which GDAL reads as its defaults:
# rasterio.Env entered from many threads at once deadlocked the first full run
# (170 threads asleep, no connection open). Timeouts and retries so a stuck
# read fails and is tried again instead of hanging.
# HTTP/1.1: over HTTP/2's multiplexed streams a stalled read sat open and
# silent for a quarter of an hour, and a timeout does not fire on a connection
# that is open. A transfer that moves nothing for 30 s is abandoned instead.
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_HTTP_VERSION="1.1",
                VSI_CACHE="TRUE", GDAL_CACHEMAX="256", GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="4",
                GDAL_HTTP_RETRY_DELAY="3", GDAL_HTTP_LOW_SPEED_TIME="30", GDAL_HTTP_LOW_SPEED_LIMIT="1")


def use_gdal_env() -> None:
    import os
    for k, v in GDAL_ENV.items():
        os.environ.setdefault(k, v)


def stack(grid: Grid, scenes: int = 8, covers: float = 0.95, **search) -> tuple[np.ndarray, list[dict]]:
    """(len(BANDS), cells, cells) reflectance medians, rows south first, and
    the scenes used. A scene counts only if it has data over `covers` of the
    chip; its clouds are masked, not the scene dropped."""
    from concurrent.futures import ThreadPoolExecutor

    use_gdal_env()
    with ThreadPoolExecutor(len(BANDS) + 1) as pool:
        return _stack(grid, scenes, covers, pool, **search)


def _stack(grid: Grid, scenes: int, covers: float, pool, **search) -> tuple[np.ndarray, list[dict]]:
    taken, used = [], []
    for item in clear_scenes(grid, **search):
        assets = item["assets"]
        if not all(b in assets for b in BANDS + ("scl",)):
            continue
        green, _ = onto(grid, assets["green"]["href"], average=False)
        if float(np.isfinite(green).mean()) < covers or float((green > 0).mean()) < covers:
            continue
        others = [b for b in BANDS if b != "green"]
        read = list(pool.map(lambda name: onto(grid, assets[name]["href"], nearest=(name == "scl"),
                                               average=None if name == "scl" else False)[0], others + ["scl"]))
        bands = dict(zip(others, read[:-1]), green=green)
        bad = np.isin(np.nan_to_num(read[-1], nan=0).round(), MASKED)
        layers = []
        for name in BANDS:
            raw = bands[name]
            scale, offset = _scale(assets[name])
            value = raw * scale + offset
            value[bad | ~np.isfinite(raw) | (raw <= 0)] = np.nan
            layers.append(value)
        taken.append(np.stack(layers))
        used.append({"id": item["id"], "date": item["properties"]["datetime"][:10],
                     "cloud": item["properties"].get("eo:cloud_cover"), "masked": round(float(bad.mean()), 3)})
        if len(taken) >= scenes:
            break
    if not taken:
        raise ValueError("no clear Sentinel-2 scene covers this chip")
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            median = np.nanmedian(np.stack(taken), axis=0)
    return median.astype("float32"), used
