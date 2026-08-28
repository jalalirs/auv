"""Bring the world's bathymetry into the platform.

Fetches a global relief grid from NOAA's ERDDAP service, keeps it exactly as it
arrived, renders an image of it for the map, and writes a description of what it
is. The platform reads that description when this job succeeds and turns the
result into a layer version with the recipe and image that produced it.

This program writes files. It holds no credential and reaches nothing but the
archive it fetches from.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy
from netCDF4 import Dataset
from PIL import Image

# Where the grid comes from. ERDDAP serves a subset of any gridded dataset
# through the request itself, so the stride below is part of the provenance:
# it says exactly which cells of the source this version contains.
SERVER = os.environ.get(
    "CORAL_ERDDAP_SERVER", "https://oceanwatch.pifsc.noaa.gov/erddap"
)
DATASET = os.environ.get("CORAL_ERDDAP_DATASET", "ETOPO_2022_v1_60s")
STRIDE = int(os.environ.get("CORAL_ERDDAP_STRIDE", "6"))

OUTPUTS = Path(os.environ.get("CORAL_OUTPUTS", "/work/outputs"))
GRID = OUTPUTS / "bathymetry.nc"
RENDERING = OUTPUTS / "elevation.png"
DESCRIPTOR = OUTPUTS / "version.json"

# The source covers longitudes 0 to 360; the platform exchanges positions in
# -180 to 180. Only the rendering is rolled, so that it draws in the projection
# the interface uses. The grid itself is kept exactly as it arrived.
SOURCE_LONGITUDE_RANGE = (0.01, 359.99)
LATITUDE_RANGE = (-89.99, 89.99)


def log(message: str) -> None:
    print(message, flush=True)


# A public archive is not obliged to be reliable, and this one occasionally
# closes a transfer part-way through. An ingestion that gave up on the first
# short read would leave the world's bathymetry missing because of a dropped
# connection, so it tries again — and checks that what arrived is what it asked
# for rather than trusting the transfer to have completed.
ATTEMPTS = int(os.environ.get("CORAL_FETCH_ATTEMPTS", "4"))
BACKOFF_SECONDS = float(os.environ.get("CORAL_FETCH_BACKOFF_SECONDS", "5"))
CHUNK = 1 << 20


def grid_url() -> str:
    """The request, which is part of the provenance: it says which cells of the
    source this version contains."""
    selector = (
        f"z[({LATITUDE_RANGE[0]}):{STRIDE}:({LATITUDE_RANGE[1]})]"
        f"[({SOURCE_LONGITUDE_RANGE[0]}):{STRIDE}:({SOURCE_LONGITUDE_RANGE[1]})]"
    )
    return f"{SERVER}/griddap/{DATASET}.nc?" + urllib.parse.quote(selector, safe="[]():,")


def attempt_fetch(url: str) -> None:
    """Fetch once, streaming to disk, and confirm what arrived is complete."""
    with urllib.request.urlopen(url, timeout=600) as response:
        if response.status != 200:
            raise RuntimeError(f"the archive answered {response.status}")
        declared = response.headers.get("Content-Length")
        with GRID.open("wb") as destination:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                destination.write(chunk)

    received = GRID.stat().st_size
    if declared is not None and received != int(declared):
        raise RuntimeError(
            f"the transfer ended early: {received} bytes of the {declared} promised"
        )

    # A file that opens and carries the variable asked for is a complete file.
    # Nothing else proves the transfer finished.
    with Dataset(GRID) as check:
        if "z" not in check.variables:
            raise RuntimeError("what arrived is not the grid that was asked for")


def fetch_grid() -> str:
    """Fetch the grid, and report the request that produced it."""
    url = grid_url()
    log(f"fetching {url}")

    for attempt in range(1, ATTEMPTS + 1):
        try:
            attempt_fetch(url)
        except Exception as failure:  # noqa: BLE001 — any failure is worth retrying
            log(f"attempt {attempt} of {ATTEMPTS} failed: {failure}")
            if attempt == ATTEMPTS:
                raise SystemExit(
                    f"the archive did not deliver the grid in {ATTEMPTS} attempts"
                ) from failure
            time.sleep(BACKOFF_SECONDS * attempt)
            continue

        log(f"fetched {GRID.stat().st_size} bytes on attempt {attempt}")
        return url

    raise SystemExit("unreachable")


def colour(elevation: numpy.ndarray) -> numpy.ndarray:
    """Colour a relief grid.

    Two ramps, because the sea floor and the land above it are different things
    and a single ramp across both hides the coastline. The mapping is stated
    here and pinned by this image's digest; it is a rendering of the grid beside
    it, and the grid is what anyone measuring anything should read.
    """
    height, width = elevation.shape
    image = numpy.zeros((height, width, 3), dtype=numpy.uint8)

    sea = elevation < 0
    land = ~sea

    # Sea: deep to shallow, 8000 m to the surface.
    depth = numpy.clip(-elevation[sea] / 8000.0, 0.0, 1.0)
    image[sea, 0] = (10 + 40 * (1 - depth)).astype(numpy.uint8)
    image[sea, 1] = (40 + 120 * (1 - depth)).astype(numpy.uint8)
    image[sea, 2] = (80 + 150 * (1 - depth)).astype(numpy.uint8)

    # Land: lowland green through upland brown to snow, 0 to 6000 m.
    altitude = numpy.clip(elevation[land] / 6000.0, 0.0, 1.0)
    image[land, 0] = (70 + 185 * altitude).astype(numpy.uint8)
    image[land, 1] = (110 + 145 * altitude).astype(numpy.uint8)
    image[land, 2] = (60 + 195 * altitude).astype(numpy.uint8)

    return image


def render(url: str) -> dict[str, str]:
    """Render the grid and report what the source said about itself."""
    with Dataset(GRID) as source:
        elevation = numpy.array(source.variables["z"][:], dtype=numpy.float32)
        longitudes = numpy.array(source.variables["longitude"][:])
        attributes = {
            name: str(source.getncattr(name))
            for name in source.ncattrs()
        }
        vertical = source.variables["z"].__dict__

    # North is up, and the grid arrives south-first.
    elevation = numpy.flipud(elevation)

    # Roll 0..360 to -180..180 so the image draws in the interface's projection.
    # The grid file is untouched; only this rendering is rearranged.
    shift = int(numpy.sum(longitudes < 180.0))
    elevation = numpy.roll(elevation, -shift, axis=1)

    Image.fromarray(colour(elevation)).save(RENDERING, optimize=True)
    log(f"rendered {elevation.shape[1]}x{elevation.shape[0]} to {RENDERING.stat().st_size} bytes")

    return {
        "title": attributes.get("title", DATASET),
        "institution": attributes.get("institution", "unstated"),
        "license": attributes.get("license", "unstated"),
        "vertical_datum": vertical.get("vert_crs_name", ""),
        "vertical_epsg": vertical.get("vert_crs_epsg", ""),
        "url": url,
    }


def describe(source: dict[str, str]) -> None:
    """Say what this is, in the terms the platform requires of any evidence."""
    vertical = source["vertical_datum"] or "unstated by the source"
    if source["vertical_epsg"]:
        vertical = f"{vertical} ({source['vertical_epsg']})"

    # ETOPO 2022 is a compilation integrating campaigns spanning decades. The
    # file carries no acquisition window, so the release year is used and the
    # absence is stated rather than a window being invented.
    descriptor = {
        # Derived from measurements by a documented method: a compilation, not
        # a measurement of its own.
        "truthClass": "analysis",
        "crsEpsg": 4326,
        "verticalDatum": vertical,
        "extent": {"west": -180.0, "south": -90.0, "east": 180.0, "north": 90.0},
        "observedFrom": "2022-01-01T00:00:00Z",
        "observedTo": "2022-12-31T23:59:59Z",
        "uncertainty": {
            "kind": "described",
            "note": (
                "Vertical accuracy varies by region and by the source dataset "
                "contributing each cell, and is not carried per cell in this "
                "grid. The source states no single figure. The time basis is "
                "the compilation's release year: it integrates campaigns "
                "spanning decades and declares no acquisition window."
            ),
        },
        "rights": source["license"].strip() or "unstated by the source",
        "attribution": f"{source['title']} — {source['institution']}",
    }

    DESCRIPTOR.write_text(json.dumps(descriptor, indent=2) + "\n")
    log(f"described this version as {descriptor['truthClass']} at EPSG:4326, {vertical}")


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    url = fetch_grid()
    source = render(url)
    describe(source)
    log(f"done in {(datetime.now(timezone.utc) - started).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
