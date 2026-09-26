"""Everything a place has produced, and everything it has not.

Each page is right on its own; together they are a directory listing,
which is not a deliverable.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader("pack", str(HERE / "pack"))
    spec = importlib.util.spec_from_loader("pack", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _a_dive(where, score=0.8, soundings=None):
    where.mkdir(parents=True, exist_ok=True)
    (where / "report.html").write_text("<!doctype html><h1>a dive</h1>")
    said = {"task": {"name": "Survey", "score": score},
            "track": {"meanFixErrorM": 2.4}}
    if soundings:
        said["bathymetry"] = {"soundings": soundings}
    (where / "mission.json").write_text(json.dumps(said))


def test_a_pack_lists_what_is_there(tmp_path):
    tool = _tool()
    _a_dive(tmp_path / "run_1", soundings=12345)
    found = []
    for kind, filename, says, how in tool.KINDS:
        at = tool.find(tmp_path, filename)
        found.append({"kind": kind, "says": says, "how": how,
                      "at": [one.relative_to(tmp_path) for one in at] if at else None,
                      "line": tool.a_line(kind, at[0]) if at else ""})
    page = tool.page("looe-key", tmp_path, found)
    assert "Survey" in page and "scored 80%" in page
    assert "12,345 soundings" in page


def test_a_pack_says_loudest_what_is_not_there(tmp_path):
    """A pack that quietly omitted the missing pieces would read as
    complete."""
    tool = _tool()
    _a_dive(tmp_path / "run_1")
    tool.sys.argv = ["pack", str(tmp_path)]
    assert tool.main() == 0
    page = (tmp_path / "index.html").read_text()
    assert "not here" in page
    assert "tools/campaign" in page and "tools/again" in page
    assert "1 of 6 kinds of page are here" in page


def test_every_dive_in_the_pack_is_linked_not_just_the_first(tmp_path):
    tool = _tool()
    for n in range(3):
        _a_dive(tmp_path / f"run_{n}")
    tool.sys.argv = ["pack", str(tmp_path)]
    tool.main()
    page = (tmp_path / "index.html").read_text()
    for n in range(3):
        assert f"run_{n}/report.html" in page


def test_a_line_that_cannot_be_read_is_a_dash_and_not_a_crash(tmp_path):
    tool = _tool()
    where = tmp_path / "run_1"
    where.mkdir()
    (where / "report.html").write_text("<h1>x</h1>")      # no mission.json beside it
    assert tool.a_line("a dive", where / "report.html") == "—"


def test_the_page_needs_nothing_to_render(tmp_path):
    tool = _tool()
    _a_dive(tmp_path / "run_1")
    tool.sys.argv = ["pack", str(tmp_path)]
    tool.main()
    page = (tmp_path / "index.html").read_text()
    for fetched in ("<script", "@import", "<link", "src=", 'href="http'):
        assert fetched not in page, fetched
    assert "-apple-system" in page


def test_the_place_page_is_the_one_whose_name_nobody_fixed(tmp_path):
    """It is called after the place. A pack that looked for a file called
    provenance.html found nothing and said the reef had never been
    described."""
    tool = _tool()
    (tmp_path / "looe-key.html").write_text("<h1>looe-key</h1>")
    (tmp_path / "provenance.json").write_text(json.dumps(
        {"columns": {"latitude": {"measured": True}, "growthForm": {"measured": False}}}))
    tool.sys.argv = ["pack", str(tmp_path)]
    tool.main()
    page = (tmp_path / "index.html").read_text()
    assert "looe-key.html" in page
    assert "2 claims, 1 of them measured" in page


def test_a_missions_own_pages_are_not_mistaken_for_the_reef(tmp_path):
    """A mission folder carries a provenance.json of its own, so "the html
    next to a provenance.json" made the first real pack call its dive
    report and its conditions page the reef, twice."""
    tool = _tool()
    _a_dive(tmp_path / "run_1")
    (tmp_path / "run_1" / "conditions.html").write_text("<h1>water</h1>")
    (tmp_path / "run_1" / "provenance.json").write_text("{}")
    assert tool.find(tmp_path, "*.html!") == []
    (tmp_path / "looe-key.html").write_text("<h1>looe-key</h1>")
    assert [one.name for one in tool.find(tmp_path, "*.html!")] == ["looe-key.html"]


def test_a_label_and_its_description_are_not_one_word(tmp_path):
    """The house `.where` is a paragraph style; inside a table cell it has
    to be told to be a line of its own."""
    tool = _tool()
    _a_dive(tmp_path / "run_1")
    tool.sys.argv = ["pack", str(tmp_path)]
    tool.main()
    page = (tmp_path / "index.html").read_text()
    assert "td.what span.where { display: block" in page


def test_the_water_row_says_what_nobody_set_first(tmp_path):
    """It is the row a reader should look at, so it leads."""
    tool = _tool()
    where = tmp_path / "run_1"
    where.mkdir()
    (where / "conditions.html").write_text("<h1>water</h1>")
    (where / "mission.json").write_text(json.dumps({"conditions": {"cameFrom": {
        "counted": {"measured": 0, "derived": 0, "chosen": 2, "assumed": 8}}}}))
    assert tool.a_line("the water", where / "conditions.html") == "8 assumed · 2 chosen"


# ── building one, rather than indexing one ───────────────────────────────────

def _a_place(tmp_path, rows=16, across=100.0):
    place = tmp_path / "somewhere"
    place.mkdir(exist_ok=True)
    import numpy as np
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
        'def PointInstancer "Coral" {\n    point3f[] positions = [(0, 0, -9)]\n'
        '    int[] protoIndices = [0]\n    float3[] scales = [(1,1,1)]\n}\n')
    return place


def test_a_pack_can_be_built_and_not_only_indexed(tmp_path, capsys):
    """A chain that lives in somebody's shell history is a chain that is
    run differently the second time."""
    tool = _tool()
    place = _a_place(tmp_path)
    into = tmp_path / "pack"
    tool.sys.argv = ["pack", str(into), "--for", str(place), "--name", "Somewhere"]
    assert tool.main() == 0
    said = capsys.readouterr().out
    assert "the whole grid" in said
    assert (into / "campaign" / "campaign.html").is_file()
    assert (into / "index.html").is_file()


def test_a_step_that_refuses_does_not_stop_the_rest(tmp_path, capsys):
    """A pack is worth having with four of its six pages, and the index
    says which four."""
    tool = _tool()
    place = _a_place(tmp_path)
    # A place whose reef the deliverable tool refuses — it says nothing
    # about its prototypes, which is how a restored older place reads.
    into = tmp_path / "pack"
    tool.sys.argv = ["pack", str(into), "--for", str(place)]
    assert tool.main() == 0
    said = capsys.readouterr().out
    assert "—" in said, "a refusal was not shown"
    assert (into / "index.html").is_file()


def test_the_cost_comes_from_the_dive_worth_costing_off(tmp_path):
    """Not the first folder alphabetically, which in the first real pack
    was the dive whose controller threw two seconds in and recorded zero
    seconds in the water."""
    tool = _tool()
    pack = tmp_path / "pack"
    for name, kind, seconds in (("a_broken", "survey", 0.0),
                                ("b_short", "survey", 300.0),
                                ("c_long", "survey", 1800.0),
                                ("d_reach", "reach", 3600.0)):
        where = pack / name
        where.mkdir(parents=True)
        (where / "mission.json").write_text(json.dumps(
            {"seconds": seconds, "task": {"kind": kind}}))
    best = tool.worth_costing_off(pack)
    assert best is not None and best.parent.name == "c_long"


def test_a_pack_with_no_dive_that_worked_ground_costs_off_nothing(tmp_path):
    tool = _tool()
    pack = tmp_path / "pack"
    where = pack / "only_a_reach"
    where.mkdir(parents=True)
    (where / "mission.json").write_text(json.dumps(
        {"seconds": 900.0, "task": {"kind": "reach"}}))
    assert tool.worth_costing_off(pack) is None
