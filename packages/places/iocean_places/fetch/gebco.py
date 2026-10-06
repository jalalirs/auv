"""GEBCO 2026 and the DCDB multibeam mosaic around a site, by range requests.

Moved from tools/surroundings, which keeps its command line and the place's
record. GEBCO's netCDF is HDF5 with the elevation as one contiguous int16
array, so each row of a box is a byte range of the file at CEDA's archive: a
few hundred kilobytes a place, not 7.5 GB. The Type Identifier Grid says what
each cell came from. The DCDB mosaic is cut to the same box by NOAA's image
service, NaN where no ship has surveyed.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import numpy as np
import requests

GEBCO = "https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2026"
ELEVATION = f"{GEBCO}/ice_surface_elevation/netcdf/GEBCO_2026.nc"
TID = f"{GEBCO}/type_identifier_grid/netcdf/gebco_2026_tid.nc"
ROWS, COLS = 43200, 86400
STEP = 1.0 / 240.0                       # 15 arc-seconds
# What each TID value means (GEBCO's documentation).
TID_MEANS = {0: "land", 10: "singlebeam", 11: "multibeam", 12: "seismic", 13: "isolated sounding",
             14: "ENC sounding", 15: "lidar", 16: "depths from optical light sensing", 17: "combination of direct methods",
             40: "predicted from satellite gravity", 41: "interpolated", 42: "digital bathymetric contours",
             43: "digital bathymetric contours from charts", 44: "multiple sources", 45: "pre-generated grid",
             46: "unknown", 70: "pre-generated grid", 71: "steering points", 72: "unknown source"}


def where_the_array_is(url: str, name: str) -> tuple[int, str]:
    """The byte offset and the type of a contiguous dataset in a remote HDF5
    file, read once in a child process (h5py over a Python file object can
    fault on the way out, and the offset is all that is wanted)."""
    probe = f'''
import io, requests, h5py
class Remote(io.RawIOBase):
    def __init__(s, url, block=1 << 16):
        s.url, s.pos, s.block, s.cache = url, 0, block, {{}}
        s.size = int(requests.head(url, allow_redirects=True).headers["content-length"])
    def readable(s): return True
    def seekable(s): return True
    def seek(s, off, whence=0):
        s.pos = off if whence == 0 else (s.pos + off if whence == 1 else s.size + off); return s.pos
    def tell(s): return s.pos
    def readinto(s, buf):
        end = min(s.size, s.pos + len(buf)); out = b""; p = s.pos
        while p < end:
            i = p // s.block
            if i not in s.cache:
                a = i * s.block
                s.cache[i] = requests.get(s.url, headers={{"Range": f"bytes={{a}}-{{min(s.size, a + s.block) - 1}}"}}).content
            off = p - i * s.block; take = s.cache[i][off:off + end - p]; out += take; p += len(take)
        buf[:len(out)] = out; s.pos = end; return len(out)
h = h5py.File(Remote("{url}"), "r")
d = h["{name}"]
print(d.id.get_offset(), d.dtype.str, d.shape[0], d.shape[1], flush=True)
'''
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=300).stdout.split()
    offset, dtype, rows, cols = int(out[0]), out[1], int(out[2]), int(out[3])
    assert (rows, cols) == (ROWS, COLS), (rows, cols)
    return offset, dtype


def where_the_tid_is(url: str) -> tuple[int, str]:
    """The TID grid is classic netCDF-3, not HDF5: its int8 array is the file's
    last variable, contiguous to the end, so it starts the grid's size before
    the end. (Checked: a cell in Riyadh reads 0, land; mid-ocean 40.)"""
    size = int(requests.head(url, allow_redirects=True, timeout=60).headers["content-length"])
    return size - ROWS * COLS, "|i1"


def box_of(url: str, name: str, i0: int, i1: int, j0: int, j1: int) -> np.ndarray:
    """Rows i0..i1 and columns j0..j1 of the grid, one range request a row."""
    offset, dtype = where_the_tid_is(url) if name == "tid" else where_the_array_is(url, name)
    size = np.dtype(dtype).itemsize
    rows = []
    for i in range(i0, i1):
        a = offset + (i * COLS + j0) * size
        b = offset + (i * COLS + j1) * size - 1
        for attempt in range(5):
            got = requests.get(url, headers={"Range": f"bytes={a}-{b}"}, timeout=60).content
            if len(got) == b - a + 1:
                break
            # A short answer is the archive having a moment, not the data.
        else:
            raise RuntimeError(f"row {i}: {len(got)} bytes, wanted {b - a + 1}, five times")
        rows.append(np.frombuffer(got, dtype=dtype))
    return np.vstack(rows)


MULTIBEAM = "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_mosaic/ImageServer/exportImage"


def multibeam(south, north, west, east, cells: int = 240):
    """The DCDB multibeam mosaic over the box, rows south to north, NaN where
    no ship has surveyed; None where none has anywhere in it. Raw float32
    (`bsq`): checked pixel by pixel against the service's own identify."""
    params = {"bbox": f"{west},{south},{east},{north}", "bboxSR": 4326, "imageSR": 4326, "size": f"{cells},{cells}",
              "format": "bsq", "pixelType": "F32", "noData": -99999, "interpolation": "RSP_NearestNeighbor", "f": "json"}
    said = requests.get(MULTIBEAM, params=params, timeout=120).json()
    raw = requests.get(said["href"], timeout=120).content
    w, h = said["width"], said["height"]
    a = np.frombuffer(raw[: w * h * 4], dtype="<f4").reshape(h, w).astype("<f4")[::-1].copy()
    a[(a == -99999) | ~np.isfinite(a) | (a < -12000) | (a > 100)] = np.nan
    return None if np.isnan(a).all() else a



def fetch_box(latitude: float, longitude: float, half_degrees: float, into: pathlib.Path) -> dict:
    """GEBCO (and any multibeam) over the box `half_degrees` around a point,
    written into `into` as surroundings.f32, surroundings_tid.u8 and
    multibeam.f32; returns the record a place keeps under "surroundings"."""
    into = pathlib.Path(into)
    h = half_degrees
    # Cell i, j is centred at lat -90 + (i + 0.5) * STEP, lon -180 + (j + 0.5) * STEP.
    i0, i1 = int((latitude - h + 90.0) / STEP), int((latitude + h + 90.0) / STEP) + 1
    j0, j1 = int((longitude - h + 180.0) / STEP), int((longitude + h + 180.0) / STEP) + 1
    height = box_of(ELEVATION, "elevation", i0, i1, j0, j1).astype("<f4")
    tid = box_of(TID, "tid", i0, i1, j0, j1).astype("u1")
    height.tofile(into / "surroundings.f32")
    tid.tofile(into / "surroundings_tid.u8")
    kinds, counts = np.unique(tid, return_counts=True)
    record = {
        "file": "surroundings.f32", "tidFile": "surroundings_tid.u8",
        "rows": int(height.shape[0]), "columns": int(height.shape[1]),
        "south": round(-90.0 + i0 * STEP, 6), "north": round(-90.0 + i1 * STEP, 6),
        "west": round(-180.0 + j0 * STEP, 6), "east": round(-180.0 + j1 * STEP, 6),
        "cellArcSeconds": 15.0,
        "from": ("measured and derived: GEBCO Compilation Group (2026) GEBCO 2026 Grid, doi:10.5285/"
                 "(see catalogue.ceda.ac.uk), public domain; read by range requests from CEDA's archive"),
        "whatEachCellIs": {TID_MEANS.get(int(k), str(int(k))): round(float(c) / tid.size, 3) for k, c in zip(kinds, counts)},
    }
    beams = multibeam(record["south"], record["north"], record["west"], record["east"])
    if beams is not None:
        beams.tofile(into / "multibeam.f32")
        record["multibeam"] = {
            "file": "multibeam.f32", "rows": int(beams.shape[0]), "columns": int(beams.shape[1]),
            "coveredShare": round(float(np.isfinite(beams).mean()), 3),
            "from": ("measured: NOAA NCEI multibeam bathymetry mosaic (IHO Data Centre for Digital Bathymetry), "
                     "3 arc-second, through its image service; NaN where no ship has surveyed")}
    return record
