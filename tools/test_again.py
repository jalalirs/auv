"""Round two, and whether it can be held against round one.

"We went back" is not comparable. Comparable means the same ground, seen
the same way — and the second of those is the one that gets missed, because
a round flown differently reads as change on the reef.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _load(name):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / name))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _tool():
    return _load("again")


def _a_place(tmp_path, across=100.0, rows=16):
    place = tmp_path / "somewhere"
    place.mkdir(exist_ok=True)
    heights = np.full((rows, rows), -10.0, dtype="<f4")
    heights.tofile(place / "seabed.f32")
    (place / "site.json").write_text(json.dumps({
        "name": "somewhere",
        "from": {"centre": {"latitude": 24.5, "longitude": -81.4},
                 "acrossMetres": across, "sampleMetres": 1.0},
        "mesh": {"heightfield": {"rows": rows, "columns": rows, "file": "seabed.f32"}},
        "layers": {"coral": "coral.usda"},
    }))
    (place / "coral.usda").write_text(
        'def PointInstancer "Coral" {\n    point3f[] positions = []\n'
        '    int[] protoIndices = []\n    float3[] scales = []\n}\n')
    return place


def _a_round(tmp_path, place, name, cells, altitude=2.0, swath=4.0, task="survey"):
    """A round: one mission folder, with what it produced and how it flew."""
    campaign = _load("campaign")
    deliver = _load("deliver")
    grid = campaign.cells_over(place, cell_m=25.0, where="all")
    centre = grid["centre"]
    features = []
    for row, column in cells:
        one = next(c for c in grid["cells"]
                   if c["row"] == row and c["column"] == column)
        latitude, longitude = deliver.where_on_earth(centre, one["x"], one["y"])
        features.append({"type": "Feature", "properties": {"what": "seen"},
                         "geometry": {"type": "Point",
                                      "coordinates": [longitude, latitude]}})
    folder = tmp_path / name / "run_1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "coverage.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}))
    (folder / "mission.json").write_text(json.dumps({
        "seconds": 900.0,
        "task": {"kind": task, "achieved": {"altitudeM": altitude, "swathM": swath}},
    }))
    return tmp_path / name


def test_the_same_ground_seen_the_same_way_is_a_repeat(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0), (0, 1), (1, 1)])
    two = _a_round(tmp_path, place, "r2", [(0, 0), (0, 1), (1, 1)])
    ground = tool.the_same_ground(place, 25.0, "all", one, two)
    alike = tool.the_same_way(tool.how_it_was_flown(one), tool.how_it_was_flown(two))
    assert ground["inBoth"] == 3 and ground["lostSinceRoundOne"] == 0
    assert {a["verdict"] for a in alike} == {"the same"}
    assert "two rounds of one survey" in tool.page("x", ground, alike)


def test_a_cell_covered_then_and_missed_now_is_a_hole_in_the_series(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0), (0, 1), (1, 1)])
    two = _a_round(tmp_path, place, "r2", [(0, 0), (2, 2)])
    ground = tool.the_same_ground(place, 25.0, "all", one, two)
    assert ground["inBoth"] == 1
    assert ground["lostSinceRoundOne"] == 2
    assert ground["newInRoundTwo"] == 1
    page = tool.page("x", ground, tool.the_same_way(
        tool.how_it_was_flown(one), tool.how_it_was_flown(two)))
    assert "ROUND ONE ONLY" in page
    assert "2 holes" in page


def test_a_round_flown_higher_is_not_a_repeat(tmp_path):
    """It will read as change on the reef, and it is not. That is the most
    expensive mistake a monitoring programme can make."""
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0)], altitude=2.0)
    two = _a_round(tmp_path, place, "r2", [(0, 0)], altitude=4.0)
    alike = tool.the_same_way(tool.how_it_was_flown(one), tool.how_it_was_flown(two))
    higher = next(a for a in alike if a["what"] == "how high it was flown")
    assert higher["verdict"] == "different" and higher["offBy"] == pytest.approx(2.0)
    ground = tool.the_same_ground(place, 25.0, "all", one, two)
    assert "not two rounds of one survey" in tool.page("x", ground, alike)


def test_a_hand_is_allowed_to_shake_a_little(tmp_path):
    """A tenth of a metre is nothing; half a metre is a different survey."""
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0)], altitude=2.0)
    two = _a_round(tmp_path, place, "r2", [(0, 0)], altitude=2.1)
    alike = tool.the_same_way(tool.how_it_was_flown(one), tool.how_it_was_flown(two))
    assert {a["verdict"] for a in alike} == {"the same"}


def test_a_different_task_is_not_a_repeat_at_any_altitude(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0)], task="survey")
    two = _a_round(tmp_path, place, "r2", [(0, 0)], task="transect")
    alike = tool.the_same_way(tool.how_it_was_flown(one), tool.how_it_was_flown(two))
    assert next(a for a in alike if a["what"] == "what was flown")["verdict"] == "different"


def test_a_round_that_did_several_things_is_not_averaged(tmp_path):
    """An average altitude is a number no dive was flown at."""
    tool = _tool()
    place = _a_place(tmp_path)
    mixed = _a_round(tmp_path, place, "r1", [(0, 0)], altitude=2.0)
    second = mixed / "run_2"
    second.mkdir()
    (second / "mission.json").write_text(json.dumps({
        "seconds": 900.0,
        "task": {"kind": "survey", "achieved": {"altitudeM": 4.0, "swathM": 4.0}}}))
    two = _a_round(tmp_path, place, "r2", [(0, 0)], altitude=3.0)
    alike = tool.the_same_way(tool.how_it_was_flown(mixed), tool.how_it_was_flown(two))
    higher = next(a for a in alike if a["what"] == "how high it was flown")
    assert higher["verdict"] == "cannot say"
    assert "an average is a number no dive was flown at" in higher["why"]


def test_the_page_needs_nothing_to_render(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    one = _a_round(tmp_path, place, "r1", [(0, 0)])
    two = _a_round(tmp_path, place, "r2", [(0, 0)])
    page = tool.page("x", tool.the_same_ground(place, 25.0, "all", one, two),
                     tool.the_same_way(tool.how_it_was_flown(one),
                                       tool.how_it_was_flown(two)))
    for fetched in ("<script", "@import", "<link", "src=", 'href="http'):
        assert fetched not in page, fetched
    assert "-apple-system" in page


def test_the_reef_is_named_by_the_reef_not_by_its_folder(tmp_path):
    """Pointed at a package, the folder is named after a build.

    `ver_01M2NCGTERKN5Q1GQE61R6VGP9` names a build of Looe Key and not Looe
    Key, so two builds of one reef would head two pages as two reefs — which
    is the exact confusion this tool exists to catch in somebody else's data.
    """
    place = tmp_path / "ver_01M2NCGTERKN5Q1GQE61R6VGP9"
    place.mkdir()
    (place / "site.json").write_text(json.dumps({"name": "looe-key"}))
    inside = (HERE / "again").read_text()
    # The name is read from the place, and the folder is only the fallback.
    assert 'json.loads((place / "site.json").read_text())["name"]' in inside
    assert "called = place.name" in inside
    assert "place.name" not in inside.split("def main(")[-1].replace(
        "called = place.name", "")


def test_a_place_that_does_not_name_itself_falls_back_to_its_folder(tmp_path):
    """Better a folder name than no name: a page with no heading is worse than
    a page headed by a directory, and the refusal belongs to whether the
    rounds can be compared rather than to what the reef is called."""
    inside = (HERE / "again").read_text()
    where = inside.index("called = json.loads")
    assert "except Exception:" in inside[where:where + 400]


def test_the_comparison_can_be_written_out_when_the_rounds_overlap():
    """The first time this ran on two rounds that actually shared ground, it
    computed the whole comparison and then died writing it.

    `covered_by` hands back `hit` keyed by the cell itself — a `(row, column)`
    tuple — which is the right shape for drawing a grid and not a shape JSON has.
    A tuple cannot be an object key, and `json.dumps`'s `default=` never sees it,
    because that handles values and not keys. Every earlier run had zero cells in
    common, so nothing had ever reached the line.
    """
    tool = _tool()
    said = {"inBoth": 3, "lostSinceRoundOne": 1, "newInRoundTwo": 2, "neither": 4,
            "first": {"cellsCovered": 3, "cellsMissed": 1,
                      "hit": {(0, 0): 2, (1, 4): 5}},
            "then": {"cellsCovered": 4, "cellsMissed": 0,
                     "hit": {(0, 0): 1}}}
    out = {k: tool.counted(v) for k, v in said.items()}
    # Writable, which is the whole point.
    json.dumps(out, indent=2)
    # And the counts survive; only the per-cell map goes.
    assert out["first"]["cellsCovered"] == 3
    assert "hit" not in out["first"]
    assert out["inBoth"] == 3


def test_the_page_still_gets_the_cells_it_draws():
    """The map is dropped from the record and not from the page: a grid with no
    cells in it is the one thing the page is for."""
    inside = (HERE / "again").read_text()
    # The page is handed `said` whole; only the JSON is filtered.
    assert "page(called, said, alike)" in inside
    assert "counted(v) for k, v in said.items()" in inside
