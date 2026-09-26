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


def test_the_place_page_is_found_by_what_sits_beside_it(tmp_path):
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


def test_a_stray_html_without_its_json_is_not_a_place_page(tmp_path):
    tool = _tool()
    (tmp_path / "notes.html").write_text("<h1>notes</h1>")
    assert tool.find(tmp_path, "*.html:provenance.json") == []


def test_a_label_and_its_description_are_not_one_word(tmp_path):
    """The house `.where` is a paragraph style; inside a table cell it has
    to be told to be a line of its own."""
    tool = _tool()
    _a_dive(tmp_path / "run_1")
    tool.sys.argv = ["pack", str(tmp_path)]
    tool.main()
    page = (tmp_path / "index.html").read_text()
    assert "td.what span.where { display: block" in page
