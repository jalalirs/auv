"""The page that says what anybody measured.

A cover figure that traces to a transect can be cited; one that came out of a
pipeline cannot, and the difference is not visible in a render.
"""

import importlib.machinery
import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader(
        "provenance", str(HERE / "provenance"))
    spec = importlib.util.spec_from_loader("provenance", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _surveyed():
    return {
        "name": "looe-key",
        "from": {"surveyed": True, "acrossMetres": 1000.0, "sampleMetres": 1.0,
                 "centre": {"latitude": 24.5, "longitude": -81.4}},
        "ground": {"surveyed": True, "hardnessFrom": "habitat polygons"},
        "reef": {"colonies": 83055, "sizesAre": "surveyed",
                 "cover": {"measured": True, "from": "a survey"}},
    }


def _grown():
    return {
        "name": "red-sea",
        "from": {"surveyed": False, "acrossMetres": 1000.0, "sampleMetres": 2.0,
                 "centre": {"latitude": 22.0, "longitude": 38.0}},
        "ground": {"surveyed": False, "hardnessFrom": "slope and relief"},
        "reef": {"colonies": 700000, "sizesAre": "grown",
                 "cover": {"measured": False, "from": "chosen on purpose"}},
    }


def test_every_row_agrees_with_itself():
    """Looe Key came out tagged "measured" with a value of "inferred from
    slope and relief" and a source saying "habitat polygons from a survey" —
    three fields disagreeing in one row, on the page whose whole job is to be
    believed."""
    tool = _tool()
    for site in (_surveyed(), _grown()):
        for row in tool.about(site, None):
            if row["kind"] == tool.MEASURED:
                assert "inferred" not in row["value"], row
                assert "derived" not in row["value"].lower(), row
            if row["kind"] == tool.DERIVED:
                assert "an observation" != row["value"], row


def test_a_surveyed_place_and_a_grown_one_do_not_read_the_same():
    tool = _tool()
    surveyed = tool.about(_surveyed(), None)
    grown = tool.about(_grown(), None)
    def count(rows, kind):
        return sum(1 for r in rows if r["kind"] == kind)
    assert count(surveyed, tool.MEASURED) > count(grown, tool.MEASURED)
    assert count(grown, tool.CHOSEN) > count(surveyed, tool.CHOSEN)


def test_derived_and_chosen_are_not_the_same_word():
    """Derived is arithmetic on something real; chosen is a person deciding.
    A page that collapsed them would be doing what this page exists to stop."""
    tool = _tool()
    assert tool.DERIVED != tool.CHOSEN
    assert tool.INK[tool.DERIVED] != tool.INK[tool.CHOSEN]


def test_a_delivered_column_that_was_measured_says_so():
    tool = _tool()
    rows = tool.about(_surveyed(), {"columns": {
        "latitude": {"measured": True, "from": "where the survey found it"},
        "growthForm": {"measured": False, "from": "assigned afterwards"}}})
    by = {r["what"]: r for r in rows}
    assert by["Column “latitude” in colonies.csv"]["kind"] == tool.MEASURED
    assert by["Column “growthForm” in colonies.csv"]["kind"] == tool.DERIVED


def test_the_page_needs_nothing_to_render():
    """Meant to survive being emailed, printed and put in a slide."""
    tool = _tool()
    out = tool.page(_surveyed(), tool.about(_surveyed(), None))
    for fetched in ("<script", "http://", "https://", "@import", "<link"):
        assert fetched not in out, fetched
    assert out.startswith("<!doctype html>")


def test_it_escapes_what_a_record_says():
    """Every string on this page comes out of a JSON file somebody wrote."""
    tool = _tool()
    site = _surveyed()
    site["ground"]["hardnessFrom"] = '<script>alert("x")</script>'
    out = tool.page(site, tool.about(site, None))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


# ── a dive ───────────────────────────────────────────────────────────────────

FLOWN = {
    "event": "conditions_from",
    "were": {"currentMetresPerSecond": 0.0, "currentHeadingDeg": 0.0,
             "visibilityM": None, "densityKgM3": 1028.9,
             "salinityPsu": 40.6, "temperatureC": 26.0,
             "significantWaveHeightM": 0.4, "waveMeanPeriodS": 6.0},
    "cameFrom": {
        "kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
        "fields": {
            "currentMetresPerSecond": {"how": "assumed", "instead": "still water"},
            "currentHeadingDeg": {"how": "assumed", "instead": "still water"},
            "visibilityM": {"how": "assumed", "instead": "whatever the water type gives"},
            "waterType": {"how": "chosen"},
            "significantWaveHeightM": {"how": "measured", "at": "2026-09-20T06:00:00Z",
                                       "from": "a Sofar Spotter buoy in the water",
                                       "through": "aqualink.org"},
            "waveMeanPeriodS": {"how": "measured", "at": "2026-09-20T06:00:00Z"},
            "temperatureC": {"how": "measured", "at": "2026-09-20T06:00:00Z"},
            "salinityPsu": {"how": "chosen"},
            "densityKgM3": {"how": "derived", "fromFields": ["salinityPsu", "temperatureC"],
                            "by": "the equation of state"},
            "depthGaugeDensityKgM3": {"how": "assumed",
                                      "instead": "a gauge right for the water it is in"},
        },
        "counted": {"measured": 3, "derived": 1, "chosen": 2, "assumed": 4},
    },
}


def _log(tmp_path):
    out = tmp_path / "red-sea-II" / "look.log"
    out.parent.mkdir()
    out.write_text('{"event": "place_open", "prims": 4}\n'
                   + __import__("json").dumps(FLOWN) + "\n")
    return out


def test_a_dive_says_which_of_its_conditions_nobody_set(tmp_path):
    """The whole point. A run against a measured sea and a run against an
    empty form both report a number for every field."""
    tool = _tool()
    said, came, name = tool.a_dive(_log(tmp_path))
    rows = {r["what"]: r for r in tool.about_dive(came, said)}
    assert name == "red-sea-II"
    assert rows["current"]["kind"] == tool.ASSUMED
    assert "still water" in rows["current"]["from"]
    assert rows["wave height"]["kind"] == tool.MEASURED
    assert "Spotter" in rows["wave height"]["from"]
    assert rows["density"]["kind"] == tool.DERIVED
    assert "equation of state" in rows["density"]["from"]


def test_an_assumed_condition_still_shows_the_number_it_was_flown_with(tmp_path):
    """Grey does not mean absent. The dive really was flown in still water —
    what is missing is anybody having asked for it."""
    tool = _tool()
    said, came, _ = tool.a_dive(_log(tmp_path))
    rows = {r["what"]: r for r in tool.about_dive(came, said)}
    assert rows["current"]["value"] == "0.00 m/s"


def test_a_dive_flown_before_any_of_this_is_refused_not_guessed(tmp_path):
    """A page of assumptions that passes for a record is worse than no page."""
    tool = _tool()
    old = tmp_path / "old-dive" / "look.log"
    old.parent.mkdir()
    old.write_text('{"event": "water_is", "type": "1C"}\n')
    assert tool.dive_of(old, tmp_path) == 1


def test_the_dive_page_needs_nothing_to_render(tmp_path):
    tool = _tool()
    said, came, name = tool.a_dive(_log(tmp_path))
    out = tool.dive_page(name, came, tool.about_dive(came, said))
    for fetched in ("<script", "http://", "https://", "@import", "<link"):
        assert fetched not in out, fetched
    assert out.startswith("<!doctype html>")
    # Four words on a dive, three on a place, and the legend carries only
    # the ones the page uses.
    assert ">assumed<" in out
