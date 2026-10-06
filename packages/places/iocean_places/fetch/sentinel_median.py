"""Sentinel-2's median true colour over a site: the clearest scenes, one median.

Moved from tools/reference, which keeps its command line and calls this.
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

AGENT = "iocean reference corpus (https://github.com/jalalirs/auv)"


def get(url: str, timeout: int = 120, data: bytes | None = None, headers=None) -> bytes:
    request = urllib.request.Request(url, data=data,
                                     headers={"User-Agent": AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return answer.read()


EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"


def from_space(into: pathlib.Path, box, scenes: int, cloud: float,
               until: str = "2030-01-01T00:00:00Z") -> dict | None:
    """Sentinel-2 true colour over the square: the median of the clearest scenes.

    A median across eight clear days takes out the glint, the waves and the odd
    cloud shadow, and leaves what the bottom looks like from space — which is
    the one view that shows a whole square kilometre of reef at once.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds
    except ImportError:
        print("  from space: needs numpy and rasterio (python -m pip install rasterio)")
        return None
    body = json.dumps({"collections": ["sentinel-2-l2a"], "bbox": list(box), "limit": 100,
                       "datetime": f"2022-01-01T00:00:00Z/{until}",
                       "query": {"eo:cloud_cover": {"lt": cloud}}}).encode()
    try:
        found = json.loads(get(EARTH_SEARCH, data=body, headers={"Content-Type": "application/json"}))
    except Exception as exc:
        print(f"  from space: could not search Earth Search ({exc})")
        return None
    items = sorted(found["features"], key=lambda f: f["properties"]["eo:cloud_cover"])[:scenes]
    stack, used = [], []
    for f in items:
        try:
            with rasterio.open(f["assets"]["visual"]["href"]) as src:
                window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *box), src.transform)
                stack.append(src.read([1, 2, 3], window=window).transpose(1, 2, 0))
                used.append({"id": f["id"], "date": f["properties"]["datetime"][:10],
                             "cloud": f["properties"]["eo:cloud_cover"]})
        except Exception as exc:
            print(f"    {f['id']}: {exc}")
    if not stack:
        return None
    h = min(a.shape[0] for a in stack); w = min(a.shape[1] for a in stack)
    median = np.median(np.stack([a[:h, :w] for a in stack]).astype("float32"), axis=0)
    np.save(into / "sentinel_median_rgb.npy", median)
    (into / "sentinel.json").write_text(json.dumps({"bbox": list(box), "scenes": used, "until": until,
                                                    "rows": h, "columns": w,
                                                    "note": "row 0 is north"}, indent=1))
    print(f"  from space: median of {len(used)} Sentinel-2 scenes, {w}x{h} at 10 m")
    return {"file": "sentinel_median_rgb.npy", "scenes": len(used), "source": "Copernicus Sentinel-2 L2A via Earth Search",
            "licence": "Copernicus open data"}


