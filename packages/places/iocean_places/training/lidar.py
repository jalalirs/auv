"""The dense labels: NOAA topobathy lidar DEMs over coral reefs.

From the public noaa-nos-coastal-lidar-pds bucket, listed and fetched over
plain HTTPS (no account, no AWS tools). Each dataset is one or many GeoTIFF
tiles in a UTM or state plane system, heights in its own vertical datum
(NAVD88, LMSL, PRVD02, GUVD04...): decimetres apart, and said in the chip's
record rather than corrected.
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

BUCKET = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
SOURCES = pathlib.Path(__file__).with_name("lidar_sources.json")


def datasets() -> list[dict]:
    return json.loads(SOURCES.read_text())["datasets"]


def files_of(slug: str) -> list[tuple[str, int]]:
    """Every GeoTIFF in a dataset, with its size: (key, bytes)."""
    out, token = [], None
    while True:
        query = {"list-type": "2", "prefix": f"dem/{slug}/"}
        if token:
            query["continuation-token"] = token
        root = ET.fromstring(urllib.request.urlopen(f"{BUCKET}/?{urllib.parse.urlencode(query)}", timeout=120).read())
        for c in root.iter(NS + "Contents"):
            key = c.find(NS + "Key").text
            if key.endswith(".tif"):
                out.append((key, int(c.find(NS + "Size").text)))
        nxt = root.find(NS + "NextContinuationToken")
        if nxt is None:
            return out
        token = nxt.text


def _get(key: str, size: int, into: pathlib.Path) -> pathlib.Path:
    path = into / pathlib.Path(key).name
    if path.is_file() and path.stat().st_size == size:
        return path
    part = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(f"{BUCKET}/{urllib.parse.quote(key)}", timeout=600) as answer, open(part, "wb") as out:
        while True:
            block = answer.read(1 << 22)
            if not block:
                break
            out.write(block)
    if part.stat().st_size != size:
        part.unlink()
        raise IOError(f"{key}: {part.stat().st_size if part.exists() else 0} bytes of {size}")
    part.rename(path)
    return path


def fetch(slug: str, into: pathlib.Path, workers: int = 8) -> list[pathlib.Path]:
    """A dataset's tiles into `into/slug`, skipping what is already there whole."""
    folder = pathlib.Path(into).expanduser() / slug
    folder.mkdir(parents=True, exist_ok=True)
    listed = files_of(slug)
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda kv: _get(kv[0], kv[1], folder), listed))


def footprints(paths: list[pathlib.Path]) -> list[tuple[pathlib.Path, tuple[float, float, float, float]]]:
    """Each tile's bounds in degrees (west, south, east, north)."""
    import rasterio
    from rasterio.warp import transform_bounds

    out = []
    for p in paths:
        with rasterio.open(p) as src:
            if src.crs is None:
                continue
            out.append((p, transform_bounds(src.crs, "EPSG:4326", *src.bounds)))
    return out


def wet(tiles: list[tuple[pathlib.Path, tuple]], every_m: float = 20.0, shallowest: float = -0.5,
        deepest: float = -30.0) -> tuple["np.ndarray", "np.ndarray", float]:
    """Where each survey measured water a satellite can see the bottom of,
    read coarsely: longitudes and latitudes of the wet samples, and the area
    each stands for. Most of a survey's square is land or open sea, and
    reading it at full resolution, chip by chip, to find that out is what
    made Tutuila's first 142 chip places take 16 minutes to refuse."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp

    lons, lats, area = [], [], every_m ** 2
    for path, _ in tiles:
        with rasterio.open(path) as src:
            # A pixel's size in metres: Hawaii's surveys are in degrees, and
            # 20 m divided by 9e-6 read every tile as a single pixel.
            pixel_m = abs(src.res[0]) * (111_000.0 if src.crs and src.crs.is_geographic else 1.0)
            step = max(1, int(round(every_m / pixel_m)))
            h = src.read(1, out_shape=(max(1, src.height // step), max(1, src.width // step)))
            nodata = src.nodata
            rows, cols = np.nonzero((h < shallowest) & (h > deepest) & ((h != nodata) if nodata is not None else True))
            if not rows.size:
                continue
            sy, sx = src.height / h.shape[0], src.width / h.shape[1]
            xs, ys = rasterio.transform.xy(src.transform, (rows + 0.5) * sy, (cols + 0.5) * sx, offset="ul")
            lon, lat = warp(src.crs, "EPSG:4326", list(np.atleast_1d(xs)), list(np.atleast_1d(ys)))
            lons.append(np.asarray(lon)); lats.append(np.asarray(lat))
    if not lons:
        return np.array([]), np.array([]), area
    return np.concatenate(lons), np.concatenate(lats), area
