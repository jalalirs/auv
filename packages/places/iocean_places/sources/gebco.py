"""Seabed 2030: GEBCO 2026 and, where ships have surveyed, the DCDB multibeam.

GEBCO's 15 arc-second grid (about 460 m) is the whole ocean floor, and its Type
Identifier Grid says what each cell came from: multibeam, single beam, optical
sensing, an interpolation, or depth predicted from satellite gravity. Read from
what tools/surroundings cut out for a place (`surroundings.f32`,
`surroundings_tid.u8` and the record in its site.json), and, when that found
any, the DCDB multibeam mosaic (`multibeam.f32`, about 90 m).

GEBCO publishes no error per cell, so the error here is chosen from the TID and
said to be: a direct measurement is good to a metre and a percent of depth,
optical sensing to two metres and a tenth, an interpolation to ten metres and
a tenth, satellite gravity to fifty metres; and a 460 m cell standing for every
square metre in it adds 2 cm a metre of cell, about nine metres, because a
reef's depth changes within one.
"""

from __future__ import annotations

import json

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance
from . import where

STEP = 1.0 / 240.0
# TID: (what it means, kind, error in metres, error per metre of depth)
TIDS = {
    0: ("land", "measured", 2.0, 0.0),
    10: ("singlebeam", "measured", 1.0, 0.01), 11: ("multibeam", "measured", 1.0, 0.01),
    12: ("seismic", "measured", 1.0, 0.01), 13: ("isolated sounding", "measured", 1.0, 0.01),
    14: ("ENC sounding", "measured", 1.0, 0.01), 15: ("lidar", "measured", 1.0, 0.01),
    16: ("depths from optical light sensing", "derived", 2.0, 0.1),
    17: ("combination of direct methods", "measured", 1.0, 0.01),
    40: ("predicted from satellite gravity", "derived", 50.0, 0.0),
    41: ("interpolated", "derived", 10.0, 0.1), 42: ("digital bathymetric contours", "derived", 10.0, 0.1),
    43: ("digital bathymetric contours from charts", "derived", 10.0, 0.1),
    44: ("multiple sources", "derived", 10.0, 0.1), 45: ("pre-generated grid", "derived", 10.0, 0.1),
    46: ("unknown", "derived", 10.0, 0.1), 70: ("pre-generated grid", "derived", 10.0, 0.1),
    71: ("steering points", "derived", 10.0, 0.1), 72: ("unknown source", "derived", 10.0, 0.1),
}
UNKNOWN = ("unknown", "derived", 10.0, 0.1)
REPRESENTS_PER_M = 0.02
CITATION = "GEBCO Compilation Group (2026) GEBCO 2026 Grid, read by range requests from CEDA's archive"


def _on(grid: Grid, field: np.ndarray, south: float, west: float, step_lat: float, step_lon: float, order: int):
    """A lat/lon raster (rows south to north, cell centres half a step in)
    onto the grid; NaN off its edge."""
    from scipy.ndimage import map_coordinates

    lon, lat = grid.lonlat()
    row = (lat - south) / step_lat - 0.5
    col = (lon - west) / step_lon - 0.5
    return map_coordinates(field.astype("float64"), [row, col], order=order, mode="constant", cval=np.nan)


class Gebco:
    name = "gebco"
    gives = ("depth",)

    def __init__(self, path: str | None = None, multibeam: bool = True, halfDegrees: float = 0.1,  # noqa: N803
                 fetch: bool = True) -> None:
        self.path, self.multibeam, self.half, self.fetch = path, bool(multibeam), float(halfDegrees), bool(fetch)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        folder = where(self.path, cache)
        # A place keeps the record in its site.json; a reference folder in surroundings.json.
        if (folder / "site.json").is_file() and "surroundings" in json.loads((folder / "site.json").read_text()):
            said = json.loads((folder / "site.json").read_text())["surroundings"]
        else:
            if not (folder / "surroundings.json").is_file():
                if not self.fetch:
                    raise ValueError(f"{self.name}: no surroundings in {folder}, and fetching is off")
                from ..fetch.gebco import fetch_box
                folder.mkdir(parents=True, exist_ok=True)
                record = fetch_box(grid.latitude, grid.longitude, self.half, folder)
                (folder / "surroundings.json").write_text(json.dumps(record, indent=1) + "\n")
            said = json.loads((folder / "surroundings.json").read_text())
        rows, cols = said["rows"], said["columns"]
        height = np.fromfile(folder / said["file"], dtype="<f4").reshape(rows, cols)
        tid = np.fromfile(folder / said["tidFile"], dtype="u1").reshape(rows, cols)
        value = _on(grid, height, said["south"], said["west"], STEP, STEP, order=1)
        kind_at = _on(grid, tid, said["south"], said["west"], STEP, STEP, order=0)
        cell_m = STEP * 111_000.0
        tids = sorted({int(k) for k in np.unique(kind_at[np.isfinite(kind_at)])})
        provenance = [Provenance(f"{self.name}:{TIDS.get(k, UNKNOWN)[0]}", TIDS.get(k, UNKNOWN)[1],
                                 f"{CITATION}; type identifier {k}, {TIDS.get(k, UNKNOWN)[0]}; error chosen from it",
                                 "public domain") for k in tids]
        error = np.full(value.shape, np.nan, dtype="float32")
        source = np.full(value.shape, Layer.NONE, dtype="u1")
        for index, k in enumerate(tids):
            at = kind_at == k
            _, _, base, per_m = TIDS.get(k, UNKNOWN)
            error[at] = base + per_m * np.abs(np.minimum(value[at], 0.0)) + REPRESENTS_PER_M * cell_m
            source[at] = index
        source[~np.isfinite(value)] = Layer.NONE
        out = [Layer(grid, "depth", value.astype("float32"), error, source, provenance)]
        beams = said.get("multibeam")
        if self.multibeam and beams and (folder / beams["file"]).is_file():
            mb = np.fromfile(folder / beams["file"], dtype="<f4").reshape(beams["rows"], beams["columns"])
            step_lat = (said["north"] - said["south"]) / beams["rows"]
            step_lon = (said["east"] - said["west"]) / beams["columns"]
            depth = _on(grid, mb, said["south"], said["west"], step_lat, step_lon, order=1)
            mb_cell = step_lat * 111_000.0
            out.append(Layer.of(grid, "depth", depth,
                                1.0 + 0.01 * np.abs(np.nan_to_num(depth)) + REPRESENTS_PER_M * mb_cell,
                                Provenance("dcdb-multibeam", "measured",
                                           "NOAA NCEI multibeam mosaic, IHO Data Centre for Digital Bathymetry, "
                                           "3 arc-second; error chosen as for a GEBCO multibeam cell", "public domain")))
        return out
