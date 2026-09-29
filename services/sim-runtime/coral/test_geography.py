"""The dive's own geometry, and the transform it shares with tools/deliver.

The platform kept every number needed to draw a track and did not keep the
track: a run's artefacts were its raw recording, and the geometry was made from
those by a tool on somebody's workstation that uploaded nothing. So anybody
asking the platform for a dive's geometry was asking for a file that had never
been put anywhere they could reach.
"""

from __future__ import annotations

import json
import math
import pathlib

import geography

HERE = pathlib.Path(__file__).resolve().parent
DELIVER = HERE.parents[2] / "tools" / "deliver"

CENTRE = {"latitude": 22.284, "longitude": 38.962}


def _a_recording(tmp_path, poses):
    (tmp_path / "poses.jsonl").write_text(
        "".join(json.dumps(p) + "\n" for p in poses))
    return tmp_path


def _deliver():
    """tools/deliver itself, loaded by path: it has no .py on it."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("deliver", str(DELIVER))
    spec = importlib.util.spec_from_loader("deliver", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_transform_agrees_with_the_one_in_deliver():
    """Copied rather than imported, deliberately — this is the inverse of a
    transform, and two halves sharing an implementation cannot be checked
    against each other. So they are checked here, against the real tool rather
    than against a third copy written in a test, which only works while they
    are two and is the whole reason for copying."""
    theirs = _deliver()
    for latitude in (0.0, 22.284, 24.54586, -33.9, 60.0):
        assert geography.metres_per_degree(latitude) == theirs.metres_per_degree(latitude)
    for x, y in ((0.0, 0.0), (137.5, -42.0), (-800.0, 1200.0)):
        assert geography.where_on_earth(CENTRE, x, y) == theirs.where_on_earth(CENTRE, x, y)


def test_a_metre_east_moves_east_and_a_metre_north_moves_north():
    here = geography.where_on_earth(CENTRE, 0.0, 0.0)
    assert here == (CENTRE["latitude"], CENTRE["longitude"])
    east = geography.where_on_earth(CENTRE, 100.0, 0.0)
    north = geography.where_on_earth(CENTRE, 0.0, 100.0)
    assert east[1] > CENTRE["longitude"] and east[0] == CENTRE["latitude"]
    assert north[0] > CENTRE["latitude"] and north[1] == CENTRE["longitude"]


def test_it_writes_two_lines_and_they_are_different_claims(tmp_path):
    """Where it was, and where it believed it was. A single line called "the
    track" would quietly be one or the other."""
    into = _a_recording(tmp_path, [
        {"t": 0.0, "position": [0.0, 0.0, -6.0], "believed": [0.0, 0.0, -6.0]},
        {"t": 1.0, "position": [10.0, 0.0, -6.0], "believed": [12.0, 1.0, -6.0]},
        {"t": 2.0, "position": [20.0, 0.0, -6.5], "believed": [25.0, 2.0, -6.5]},
    ])
    wrote = geography.write_track(into, {"from": {"centre": CENTRE}})
    assert wrote["poses"] == 3 and wrote["believed"] == 3

    said = json.loads((into / "track.geojson").read_text())
    assert len(said["features"]) == 2
    was, thought = said["features"]
    assert "actually was" in was["properties"]["what"]
    assert "believed" in thought["properties"]["what"]
    assert was["geometry"]["coordinates"] != thought["geometry"]["coordinates"]

    # And the error is the distance between them, not something rounder.
    assert wrote["worstFixErrorM"] == round(math.hypot(5.0, 2.0), 3)


def test_a_dive_that_never_knew_where_it_was_gets_one_line(tmp_path):
    into = _a_recording(tmp_path, [
        {"t": 0.0, "position": [0.0, 0.0, -6.0]},
        {"t": 1.0, "position": [10.0, 0.0, -6.0]},
    ])
    wrote = geography.write_track(into, {"from": {"centre": CENTRE}})
    said = json.loads((into / "track.geojson").read_text())
    assert len(said["features"]) == 1
    assert wrote["believed"] == 0 and wrote["worstFixErrorM"] is None


def test_a_place_that_cannot_say_where_it_is_gets_no_geojson(tmp_path):
    """A tank has no centre. Site-local metres written as degrees would land
    somewhere real, which is worse than writing nothing."""
    into = _a_recording(tmp_path, [{"t": 0.0, "position": [0.0, 0.0, -1.0]}])
    assert geography.write_track(into, {"from": {}}) is None
    assert geography.write_track(into, None) is None
    assert not (into / "track.geojson").exists()


def test_a_half_written_pose_line_does_not_lose_the_dive(tmp_path):
    """poses.jsonl is written line by line as the dive runs, so the last line
    of a killed one is whatever had been flushed."""
    into = tmp_path
    (into / "poses.jsonl").write_text(
        json.dumps({"t": 0.0, "position": [0.0, 0.0, -6.0]}) + "\n"
        + json.dumps({"t": 1.0, "position": [5.0, 0.0, -6.0]}) + "\n"
        + '{"t": 2.0, "position": [10.0, 0.0')
    wrote = geography.write_track(into, {"from": {"centre": CENTRE}})
    assert wrote["poses"] == 2


def test_the_csv_carries_the_fix_error_per_pose(tmp_path):
    into = _a_recording(tmp_path, [
        {"t": 0.0, "position": [0.0, 0.0, -6.0], "believed": [3.0, 4.0, -6.0],
         "altitudeM": 2.5},
    ])
    geography.write_track(into, {"from": {"centre": CENTRE}})
    rows = (into / "track.csv").read_text().splitlines()
    assert "fixErrorM" in rows[0] and "altitudeM" in rows[0]
    assert rows[1].endswith("5.0")           # hypot(3, 4)


def test_it_reads_the_place_s_own_record_not_the_replay_chart(tmp_path):
    """Two different things wear the word "site" in this runtime.

    The recorder's `_site` is the coarse chart a replay draws — rows, columns,
    heights, the coral — assembled for the console, and it carries no latitude
    at all. The first dive flown with this read that one, got no centre, wrote
    no track, and reported nothing wrong. It was right not to write one; it was
    reading the wrong thing.
    """
    city = tmp_path / "city"
    city.mkdir()
    (city / "site.json").write_text(json.dumps({"from": {"centre": CENTRE}}))

    class Dive:
        brief = {"cityPath": str(city)}

    said = geography.where_the_place_is(Dive())
    assert geography.centre_of(said) == CENTRE

    # And the chart a replay gets, which is the thing that was being read.
    chart = {"rows": 512, "columns": 512, "acrossM": 3000.0, "heights": [],
             "coral": [], "deepestM": 21.59, "shallowestM": 0.0}
    assert geography.centre_of(chart) is None


def test_a_dive_with_no_package_mounted_does_not_raise(tmp_path):
    class Dive:
        brief = {"cityPath": str(tmp_path / "nowhere")}

    assert geography.where_the_place_is(Dive()) is None
    assert geography.where_the_place_is(object()) is None
