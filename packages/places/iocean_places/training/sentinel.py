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
    with urllib.request.urlopen(request, timeout=120) as answer:
        return json.loads(answer.read()).get("features", [])


def _scale(asset: dict) -> tuple[float, float]:
    band = (asset.get("raster:bands") or [{}])[0]
    return float(band.get("scale", 1e-4)), float(band.get("offset", 0.0))


def stack(grid: Grid, scenes: int = 8, covers: float = 0.95, **search) -> tuple[np.ndarray, list[dict]]:
    """(len(BANDS), cells, cells) reflectance medians, rows south first, and
    the scenes used. A scene counts only if it has data over `covers` of the
    chip; its clouds are masked, not the scene dropped."""
    taken, used = [], []
    for item in clear_scenes(grid, **search):
        assets = item["assets"]
        if not all(b in assets for b in BANDS + ("scl",)):
            continue
        green, _ = onto(grid, assets["green"]["href"], average=False)
        if float(np.isfinite(green).mean()) < covers or float((green > 0).mean()) < covers:
            continue
        scl, _ = onto(grid, assets["scl"]["href"], nearest=True)
        bad = np.isin(np.nan_to_num(scl, nan=0).round(), MASKED)
        layers = []
        for name in BANDS:
            raw = green if name == "green" else onto(grid, assets[name]["href"], average=False)[0]
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
