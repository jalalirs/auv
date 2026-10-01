"""Where the dive went, on the Earth, written beside its recording.

The platform kept every number needed to draw a dive's track and did not keep
the track. A run's artefacts were its raw recording — poses.jsonl and the rest —
and the geometry was made from those by `tools/deliver`, which runs on somebody's
workstation against a directory on disk. Nothing uploaded what it produced, so
`track.geojson` existed only where a person had run the tool, and anybody asking
the platform for a dive's geometry — an operator, a customer, an assistant over
MCP — was asking for a file that had never been put anywhere they could reach.

So the dive writes its own. The worker uploads everything in the recording
directory, and this puts two more files in it.

**Two lines, and they are not the same claim.** Where the vehicle *was* comes
from the simulator, which is the only thing that knows. Where it *believed* it
was comes from its own navigation, which is what it actually flew on. The
distance between them is the whole of what a positioning technology buys, and a
single line labelled "the track" would quietly be one or the other.

What is *not* here is the place-level product: the colony inventory, the cover
raster. That belongs to a place rather than to a dive, `tools/deliver` makes it,
and a dive has no business writing it.
"""

from __future__ import annotations

import csv
import json
import math
import pathlib

# The same expression tools/deliver and tools/make-site use, copied rather than
# imported and deliberately so — this is the inverse of a transform, and a
# transform whose forward and backward halves share an implementation cannot be
# checked by comparing them. `test_geography.py` holds this against deliver's
# and would not if they were one function.
def metres_per_degree(latitude: float) -> tuple[float, float]:
    radians = math.radians(latitude)
    east = 111412.84 * math.cos(radians) - 93.5 * math.cos(3 * radians)
    north = 111132.92 - 559.82 * math.cos(2 * radians) + 1.175 * math.cos(4 * radians)
    return east, north


def where_on_earth(centre: dict, x: float, y: float) -> tuple[float, float]:
    """Site-local metres back to latitude and longitude.

    x is east and y is north of the centre, which is how every place on this
    platform is laid out: the origin is the middle of the site.
    """
    east, north = metres_per_degree(float(centre["latitude"]))
    return (float(centre["latitude"]) + y / north,
            float(centre["longitude"]) + x / east)


def centre_of(site: dict | None) -> dict | None:
    """The place's centre, if the place says where it is.

    A tank does not, and a constructed square may not. Without one there is no
    Earth to put the track on, and a GeoJSON of site-local metres pretending to
    be degrees would be worse than no file: it would land somewhere real.
    """
    if not site:
        return None
    centre = ((site.get("from") or {}).get("centre")) or site.get("centre")
    if not centre:
        return None
    if centre.get("latitude") is None or centre.get("longitude") is None:
        return None
    return centre


def where_the_place_is(dive) -> dict | None:
    """The place's own site.json, off the mounted package.

    Not the recorder's `_site`, which is a different thing wearing the same
    word: that is the coarse chart a replay draws — rows, columns, heights, the
    coral — assembled for the console and carrying no latitude at all. Asking it
    where on Earth the dive was gets `None`, which is why the first dive flown
    with this wrote no track and said nothing was wrong. It was right not to
    write one; it was reading the wrong thing.

    The package has the real record, at the path the dive was given.
    """
    try:
        city = pathlib.Path(dive.brief.get("cityPath", "/dive/city"))
        return json.loads((city / "site.json").read_text())
    except Exception:
        return None


def write_track(into: pathlib.Path, site: dict | None) -> dict | None:
    """Read poses.jsonl back and write track.csv and track.geojson beside it.

    Returns what it wrote, or None when the place cannot say where on Earth it
    is. Never raises into the dive: a recording that is missing its geometry is
    worth more than a dive that failed at the very end while writing a file.
    """
    poses = into / "poses.jsonl"
    if not poses.is_file():
        return None
    centre = centre_of(site)
    if centre is None:
        return None

    flown: list[list[float]] = []
    thought: list[list[float]] = []
    rows: list[dict] = []
    worst, total, believed_count = 0.0, 0.0, 0

    with poses.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                pose = json.loads(line)
            except json.JSONDecodeError:
                continue
            at = pose.get("position") or pose.get("p")
            if not at or len(at) < 3:
                continue
            x, y, z = float(at[0]), float(at[1]), float(at[2])
            latitude, longitude = where_on_earth(centre, x, y)
            flown.append([round(longitude, 8), round(latitude, 8)])
            row = {
                "t": pose.get("t"),
                "latitude": round(latitude, 8), "longitude": round(longitude, 8),
                "depthM": round(-z, 3),
                "altitudeM": pose.get("altitudeM"),
            }
            believed = pose.get("believed")
            if believed and len(believed) >= 2:
                bx, by = float(believed[0]), float(believed[1])
                blat, blon = where_on_earth(centre, bx, by)
                thought.append([round(blon, 8), round(blat, 8)])
                off = math.hypot(bx - x, by - y)
                worst = max(worst, off)
                total += off
                believed_count += 1
                row["believedLatitude"] = round(blat, 8)
                row["believedLongitude"] = round(blon, 8)
                row["fixErrorM"] = round(off, 3)
            rows.append(row)

    if not rows:
        return None

    with (into / "track.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    features = [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": flown},
        "properties": {
            "what": "where the vehicle actually was",
            "from": "the simulator, which is the only thing that knows",
        },
    }]
    if thought:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": thought},
            "properties": {
                "what": "where the vehicle believed it was",
                "from": "its own navigation, which is what it flew on",
            },
        })
    (into / "track.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}, indent=1) + "\n")

    return {
        "poses": len(rows),
        "believed": believed_count,
        "worstFixErrorM": round(worst, 3) if believed_count else None,
        "meanFixErrorM": round(total / believed_count, 3) if believed_count else None,
    }


# ── what a survey actually saw ───────────────────────────────────────────────

def write_coverage(into: pathlib.Path, site: dict | None, geometry: dict | None) -> dict | None:
    """The cells the camera's footprint passed over, as ground on the Earth.

    The same arithmetic as tools/deliver's coverage_file, so a coverage drawn
    from the dive and one drawn later from its recording are the same file. The
    task already kept the grid — a covering task marks every half-metre cell its
    footprint falls on — so this only puts it somewhere the platform can hand
    over. A dive that was not asked to cover anything has no rectangle, and
    writes nothing: coverage of a plot nobody named is not a number.

    Cells rather than a raster on purpose, as deliver says: the rectangle is
    stated along the vehicle's own heading, so it is square to the mission and
    not to north, and an axis-aligned grid of it would be a resampling presented
    as a measurement.
    """
    import numpy as np

    centre = centre_of(site)
    if centre is None or not geometry:
        return None
    seen = geometry.get("seen") or {}
    corners = geometry.get("rectangle") or []
    cells, rows, columns = seen.get("cells"), seen.get("rows"), seen.get("columns")
    if not cells or not rows or not columns or len(corners) != 4:
        return None

    flags = np.unpackbits(np.array(cells, dtype=np.uint8))[:rows * columns]
    flags = flags.reshape(rows, columns)
    origin = np.array([corners[0]["x"], corners[0]["y"]], dtype=float)
    along = (np.array([corners[1]["x"], corners[1]["y"]], dtype=float) - origin) / columns
    up = (np.array([corners[3]["x"], corners[3]["y"]], dtype=float) - origin) / rows

    def lonlat(x, y):
        latitude, longitude = where_on_earth(centre, float(x), float(y))
        return [round(longitude, 8), round(latitude, 8)]

    features = [{
        "type": "Feature",
        "properties": {"what": "the rectangle it was asked to cover"},
        "geometry": {"type": "Polygon", "coordinates": [[
            lonlat(c["x"], c["y"]) for c in corners + [corners[0]]]]},
    }]
    for row in range(rows):
        for column in range(columns):
            if not flags[row, column]:
                continue
            at = origin + along * (column + 0.5) + up * (row + 0.5)
            features.append({"type": "Feature", "properties": {"what": "seen"},
                             "geometry": {"type": "Point",
                                          "coordinates": lonlat(at[0], at[1])}})
    (into / "coverage.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}, indent=1) + "\n")

    covered = int(flags.sum())
    each = float(np.linalg.norm(along)) * float(np.linalg.norm(up))
    wide = float(np.linalg.norm(along)) * columns
    deep = float(np.linalg.norm(up)) * rows
    return {"cells": int(rows * columns), "seen": covered,
            "fraction": round(covered / float(rows * columns), 4),
            "rectangleM2": round(wide * deep, 1),
            "seenM2": round(covered * each, 1)}


# ── what each of those files is ──────────────────────────────────────────────

TRUTH, BELIEVED, PLANNED = "truth", "believed", "planned"


def provenance(has_coverage: bool, has_planting: bool = False) -> dict:
    """What each column of a dive's product is, and that none of it is a reef.

    The same words as tools/deliver's mission_provenance, held against it by a
    test. A dive that hands over geometry without this is handing over numbers
    nobody can tell apart: where the vehicle was and where it believed it was
    are both latitudes, and they are not the same claim.
    """
    columns = {
        "latitude / longitude": {"kind": TRUTH,
            "from": "where the vehicle was, from the simulator, put on the Earth by "
                    "inverting the expression the place was sampled with"},
        "depthM / altitudeM / headingDeg": {"kind": TRUTH, "from": "the simulator's own state"},
        "believedLatitude / believedLongitude": {"kind": BELIEVED,
            "from": "the vehicle's navigation — what it would have logged, errors and all"},
        "fixErrorM": {"kind": "derived",
            "from": "the distance between the two above. Only a simulator can write this column"},
    }
    if has_planting:
        columns["markLatitude / markLongitude"] = {"kind": PLANNED,
            "from": "where the plan asked for a coral"}
        columns["plantedLatitude / plantedLongitude"] = {"kind": TRUTH,
            "from": "where the coral actually went, which is where the vehicle actually was"}
        columns["errorM / onTheMark"] = {"kind": "derived",
            "from": "the distance from the mark, against the tolerance the mission stated"}
    if has_coverage:
        columns["coverage.geojson"] = {"kind": TRUTH,
            "from": "the cells the camera's footprint actually passed over"}
    return {
        "about": "A flown mission, in a simulator. Nothing here is an observation of a "
                 "real reef or a real vehicle: it is what happened in a model whose "
                 "own provenance is in the place's provenance.json.",
        "why it is worth having": "Every row carries both where the vehicle was and "
                                  "where it believed it was. A real vehicle cannot "
                                  "produce the first column.",
        "columns": columns,
    }


def write_provenance(into: pathlib.Path, has_coverage: bool,
                     has_planting: bool = False) -> None:
    (into / "provenance.json").write_text(
        json.dumps(provenance(has_coverage, has_planting), indent=1) + "\n")
