"""Turning a place into what a marine department asks for.

A score and a video is not a deliverable, and a deliverable that does not say
which of its numbers anybody measured is worse than none: it gets cited back
as though the model had measured them.
"""

import csv
import importlib.machinery
import importlib.util
import json
import math
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename=None):
    loader = importlib.machinery.SourceFileLoader(
        name, str(HERE / (filename or name)))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _deliver():
    return _load("deliver")


def _make_site():
    return _load("make_site", "make-site")


def test_the_georeference_is_the_inverse_of_how_the_place_was_built():
    """`tools/deliver` carries its own copy of `metres_per_degree` on purpose:
    a transform whose forward and backward halves share an implementation
    cannot be checked by comparing them. This is that check."""
    deliver, make_site = _deliver(), _make_site()
    for latitude in (-40.0, 0.0, 21.45, 24.54586, 24.5, 60.0):
        assert deliver.metres_per_degree(latitude) == pytest.approx(
            make_site.metres_per_degree(latitude), rel=1e-12)


def test_a_colony_comes_back_where_it_was_put():
    """Round-trip a site-local position out to the Earth and back through the
    forward transform the place was sampled with."""
    deliver, make_site = _deliver(), _make_site()
    centre = {"latitude": 24.54586, "longitude": -81.4072}
    east, north = make_site.metres_per_degree(centre["latitude"])
    for x, y in ((0.0, 0.0), (-160.4, -14.33), (480.0, -499.0), (12.5, 333.0)):
        latitude, longitude = deliver.where_on_earth(centre, x, y)
        back_x = (longitude - centre["longitude"]) * east
        back_y = (latitude - centre["latitude"]) * north
        assert back_x == pytest.approx(x, abs=1e-6)
        assert back_y == pytest.approx(y, abs=1e-6)


def test_north_and_east_are_not_swapped():
    """The one error in a georeference that puts a reef in the wrong country
    and produces no warning of any kind."""
    deliver = _deliver()
    centre = {"latitude": 24.0, "longitude": -81.0}
    north = deliver.where_on_earth(centre, 0.0, 1000.0)
    east = deliver.where_on_earth(centre, 1000.0, 0.0)
    assert north[0] > centre["latitude"] and north[1] == pytest.approx(centre["longitude"])
    assert east[1] > centre["longitude"] and east[0] == pytest.approx(centre["latitude"])


def test_a_degree_of_longitude_is_shorter_further_north():
    deliver = _deliver()
    assert (deliver.metres_per_degree(60.0)[0]
            < deliver.metres_per_degree(24.0)[0]
            < deliver.metres_per_degree(0.0)[0])


def test_a_surveyed_size_is_the_measurement_and_a_grown_one_is_not():
    """On a surveyed reef the instancer's scale *is* the diameter the survey
    recorded, halved. On a grown reef it is a draw against a prototype. The
    inventory must not present the second as though it were the first."""
    deliver = _deliver()
    colonies = {"which": [0, 1], "scale": [(0.25, 0.25, 0.25), (0.5, 0.5, 0.5)]}

    surveyed = deliver.sizes_of(colonies, None, surveyed=True)
    assert surveyed["acrossM"] == pytest.approx([0.5, 1.0])
    assert surveyed["m2"] == pytest.approx(
        [math.pi * 0.0625, math.pi * 0.25])

    grown = deliver.sizes_of(colonies, [2.0, 2.0], surveyed=False)
    assert grown["m2"] == pytest.approx([2.0 * 0.0625, 2.0 * 0.25])


def test_it_refuses_a_place_that_does_not_say_what_its_prototypes_are():
    """Its first version worked the growth forms out of the USD, assuming the
    prototype index was kind times variants plus variant and reading the names
    off `reef.kinds` — which on a surveyed place is a histogram of what the
    survey counted. Every row of a published CSV came out "low" or "unknown"
    and every footprint was a hundred times too small, and it looked like a
    reef with no cover on it rather than like an error."""
    deliver = _deliver()
    with pytest.raises(SystemExit):
        deliver.prototypes_in({"name": "somewhere", "reef": {"kinds": {"low": 5}}})


def test_a_place_with_no_centre_cannot_be_delivered(tmp_path):
    """A deliverable without a georeference is a picture."""
    deliver = _deliver()
    place = tmp_path / "nowhere"
    place.mkdir()
    (place / "site.json").write_text(json.dumps({"name": "nowhere", "from": {}}))
    with pytest.raises(SystemExit):
        deliver.deliver(place, tmp_path / "out")


def test_the_grid_is_written_north_first(tmp_path):
    """Row 0 of the array is the south edge and an ASCII grid is written from
    the north down. This is the same flip every texture here needs and it is
    the one that puts a reef a mile from where the survey put it."""
    deliver = _deliver()
    grid = np.zeros((4, 4))
    grid[0, 0] = 1.0          # south-west corner
    deliver.write_grid(tmp_path, grid, {"latitude": 24.0, "longitude": -81.0},
                       20.0, 5.0)
    lines = (tmp_path / "cover.asc").read_text().splitlines()
    assert lines[0].split()[1] == "4" and lines[1].split()[1] == "4"
    assert float(lines[2].split()[1]) == pytest.approx(-10.0)
    # Six header lines, then north to south: the 1.0 is on the last row.
    assert float(lines[-1].split()[0]) == pytest.approx(1.0)
    assert float(lines[6].split()[0]) == pytest.approx(0.0)
    assert "Azimuthal_Equidistant" in (tmp_path / "cover.prj").read_text()


def test_provenance_marks_the_growth_form_unmeasured_even_on_a_survey():
    """A detector that found a colony in an orthomosaic found a blob of a size
    and a colour. Which growth form it is was assigned afterwards, and on a
    surveyed reef it is the one column that is not an observation while
    everything beside it is."""
    deliver = _deliver()
    said = deliver.provenance({
        "name": "looe-key",
        "from": {"surveyed": True, "centre": {"latitude": 24.5, "longitude": -81.4}},
        "reef": {"sizesAre": "surveyed", "cover": {"measured": True}},
    })
    assert said["columns"]["growthForm"]["measured"] is False
    assert said["columns"]["latitude"]["measured"] is True
    assert said["columns"]["acrossM"]["measured"] is True


def test_provenance_marks_a_grown_reef_as_grown():
    deliver = _deliver()
    said = deliver.provenance({
        "name": "red-sea",
        "from": {"surveyed": False, "centre": {"latitude": 22.0, "longitude": 38.0}},
        "reef": {"sizesAre": "grown", "cover": {"measured": False}},
    })
    for column in ("latitude", "longitude", "acrossM", "footprintM2",
                   "growthForm"):
        assert said["columns"][column]["measured"] is False, column
    said_first = said["readThisFirst"]
    assert "are not real colonies" in said_first
    assert "observation of a living animal" in said_first


def test_cover_is_measured_by_the_one_function_and_not_by_this_tool():
    """This had two denominators of its own before it had none.

    First it divided by every five-metre cell with a colony in it, which is
    only the reef's ground where the colonies are dense enough to fill a cell;
    Al Fahal read 9.1% instead of 52.7% and the error flattered exactly the
    three places whose density nobody has checked. Then it divided by the
    ground the builder recorded, and summed areas without saturating them, and
    Red Sea came back 110.78% covered.

    It does not compute cover at all now. `reef.cover_over` does, here and in
    both builders, on whatever colonies it is handed.
    """
    source = (HERE / "deliver").read_text()
    assert "reef_tools.cover_over(" in source
    assert "grew_over" not in source
    assert "def cover_raster" not in source


def test_the_shares_of_each_form_add_up_to_the_cover_they_are_shares_of():
    """Per form it is a share of what is covered, not the form's own area over
    the ground: that does not saturate, so on a crowded reef the parts would
    add to more than the whole."""
    deliver = _deliver()
    source = (HERE / "deliver").read_text()
    assert 'covered * seen["m2"] / max(piled, 1e-9)' in source

def test_the_raster_it_writes_is_the_one_it_measured():
    """`deliver` used to build its own grid with its own saturation beside the
    summary that had another. Two implementations of one thing is how there
    came to be two covers with the same name."""
    source = (HERE / "deliver").read_text()
    assert "def cover_raster" not in source
    assert 'grid = measured["grid"]' in source


# ── a flown mission ──────────────────────────────────────────────────────────

CENTRE = {"latitude": 22.305, "longitude": 38.97}


def _recording(tmp_path, *, place=True, marks=True):
    into = tmp_path / "run_TEST" / "recording"
    into.mkdir(parents=True)
    manifest = {
        "place": ({"name": "red-sea", "centre": CENTRE, "acrossMetres": 1000.0,
                   "sampleMetres": 1.96, "surveyed": False} if place else None),
        "positioning": {"kind": "usbl"},
        "seconds": 120.0,
        "geometry": ({"marks": [{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0}],
                      "planted": [{"x": 0.3, "y": 0.0}, {"x": 5.0, "y": 0.0}]}
                     if marks else {}),
        "task": {"kind": "outplant", "name": "Outplant coral", "score": 0.5,
                 "achieved": {"toleranceM": 1.0}},
        "conditions": {"waterType": "II", "cameFrom": {
            "kind": "constructed",
            "fields": {"waterType": {"how": "chosen"},
                       "currentMetresPerSecond": {"how": "assumed", "instead": "still water"}},
            "counted": {"measured": 0, "derived": 0, "chosen": 1, "assumed": 1}}},
    }
    (into / "manifest.json").write_text(json.dumps(manifest))
    lines = []
    for n in range(3):
        lines.append(json.dumps({
            "t": n * 0.2, "position": [float(n), 0.0, -7.0], "depthM": 7.0,
            "altitudeM": 2.0, "headingDeg": 90.0,
            "believed": [float(n) + 0.5, 0.0, -7.0]}))
    (into / "poses.jsonl").write_text("\n".join(lines) + "\n")
    return into


def test_a_mission_puts_its_track_on_the_earth(tmp_path):
    tool = _deliver()
    made = tool.deliver_dive(_recording(tmp_path), tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / "track.csv").open()))
    assert len(rows) == 3
    # Two metres east of the centre is two metres east on the Earth, which is
    # the same claim the place makes about itself.
    east, _ = tool.metres_per_degree(CENTRE["latitude"])
    assert float(rows[2]["longitude"]) == pytest.approx(
        CENTRE["longitude"] + 2.0 / east, abs=1e-9)
    assert float(rows[2]["latitude"]) == pytest.approx(CENTRE["latitude"], abs=1e-9)
    assert made["track"]["worstFixErrorM"] == pytest.approx(0.5)


def test_the_track_carries_both_where_it_was_and_where_it_thought_it_was(tmp_path):
    """The column no real vehicle can produce, and the reason for the file."""
    tool = _deliver()
    tool.deliver_dive(_recording(tmp_path), tmp_path / "out")
    drawn = json.loads((tmp_path / "out" / "track.geojson").read_text())
    what = [f["properties"]["what"] for f in drawn["features"]]
    assert "where the vehicle actually was" in what
    assert "where the vehicle believed it was" in what
    assert all(f["geometry"]["type"] == "LineString" for f in drawn["features"])


def test_a_planting_record_says_how_far_each_coral_missed(tmp_path):
    tool = _deliver()
    made = tool.deliver_dive(_recording(tmp_path), tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / "planting.csv").open()))
    assert [r["onTheMark"] for r in rows] == ["yes", "no"]
    assert float(rows[0]["errorM"]) == pytest.approx(0.3)
    assert float(rows[1]["errorM"]) == pytest.approx(3.0)
    assert made["planting"] == {"planted": 2, "of": 2, "onTheMark": 1, "toleranceM": 1.0}


def test_a_recording_that_cannot_say_where_it_was_is_refused(tmp_path):
    """Rather than writing a track in metres from a centre nobody wrote down."""
    tool = _deliver()
    with pytest.raises(SystemExit):
        tool.deliver_dive(_recording(tmp_path, place=False), tmp_path / "out")


def test_a_mission_ships_the_water_it_was_flown_in(tmp_path):
    tool = _deliver()
    tool.deliver_dive(_recording(tmp_path), tmp_path / "out")
    page = (tmp_path / "out" / "conditions.html").read_text()
    assert "nobody said — still water" in page


def test_the_mission_provenance_does_not_claim_anything_was_measured(tmp_path):
    tool = _deliver()
    tool.deliver_dive(_recording(tmp_path), tmp_path / "out")
    said = json.loads((tmp_path / "out" / "provenance.json").read_text())
    kinds = {c["kind"] for c in said["columns"].values()}
    assert "measured" not in kinds
    assert tool.TRUTH in kinds and tool.BELIEVED in kinds and tool.PLANNED in kinds


def test_a_survey_writes_what_it_actually_saw(tmp_path):
    """Cells, not an axis-aligned raster: a survey rectangle is square to the
    mission's heading and not to north."""
    tool = _deliver()
    into = _recording(tmp_path, marks=False)
    manifest = json.loads((into / "manifest.json").read_text())
    manifest["task"] = {"kind": "survey", "name": "Survey", "score": 0.5, "achieved": {}}
    manifest["geometry"] = {
        "rectangle": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0},
                      {"x": 4.0, "y": 4.0}, {"x": 0.0, "y": 4.0}],
        "seen": {"rows": 2, "columns": 2,
                 "cells": list(np.packbits(np.array([[1, 0], [0, 1]], dtype=np.uint8)).tolist())},
    }
    (into / "manifest.json").write_text(json.dumps(manifest))
    made = tool.deliver_dive(into, tmp_path / "out")
    assert made["coverage"] == {"cells": 4, "seen": 2, "fraction": 0.5}
    drawn = json.loads((tmp_path / "out" / "coverage.geojson").read_text())
    assert sum(1 for f in drawn["features"] if f["properties"]["what"] == "seen") == 2
    assert drawn["features"][0]["geometry"]["type"] == "Polygon"
