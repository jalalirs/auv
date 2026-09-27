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


def test_every_page_this_platform_prints_is_one_stylesheet(tmp_path):
    """There were three, near-identical and drifting. A house style that has
    to be copied is a house style that stops being one, and these pages go in
    front of the same people, often on the same day."""
    tool = _tool()
    loader = importlib.machinery.SourceFileLoader("deliver", str(HERE / "deliver"))
    spec = importlib.util.spec_from_loader("deliver", loader)
    deliver = importlib.util.module_from_spec(spec)
    loader.exec_module(deliver)
    # Written down once: the stylesheet lives in `provenance` and nothing
    # else declares one.
    assert (HERE / "deliver").read_text().count("color-scheme: light") == 0
    assert (HERE / "provenance").read_text().count("color-scheme: light") == 1
    pages = [tool.page(_surveyed(), tool.about(_surveyed(), None)),
             tool.index([{"name": "a", "about": "", "measured": 1, "derived": 0, "chosen": 0}]),
             tool.dive_page("a dive", FLOWN["cameFrom"],
                            tool.about_dive(FLOWN["cameFrom"], FLOWN["were"]))]
    for page in pages:
        assert "-apple-system" in page, "a page went out with no stylesheet in it"
        assert "%(style)s" not in page
    assert deliver.the_provenance_tool().STYLE is not None


def test_every_page_is_hung_on_one_skeleton():
    """The stylesheet was pulled into one place; the *shape* was still
    copied into six tools, which is how the same small CSS fault got fixed
    twice in one day in two files."""
    for name in ("provenance", "deliver", "rehearsal", "campaign", "again", "pack"):
        source = (HERE / name).read_text()
        assert "<!doctype html>" not in source or name == "provenance", (
            f"{name} still carries a page of its own")
    # And the one that does carry it carries exactly one.
    assert (HERE / "provenance").read_text().count("<!doctype html>") == 1


# ── a row's three fields have to agree ───────────────────────────────────────
#
# This has now bitten twice. A row tagged measured with a value reading
# "inferred from slope and relief" and a source naming a survey; and a row
# tagged chosen, "83,055", "from the USGS SQUID-5 survey". Both times the
# tag came out of one field and the words out of another.

SURVEY_WORDS = ("survey", "transect", "orthomosaic", "measured", "observed",
                "sounded", "counted by")


def _a_place_built_before_cover():
    """A place from before the reef recorded its cover — which is how the
    restored Looe Key reads, and how any older place reads."""
    return {"name": "somewhere",
            "from": {"surveyed": True, "acrossMetres": 1000.0, "sampleMetres": 1.96,
                     "centre": {"latitude": 24.5, "longitude": -81.4}},
            "ground": {"surveyed": True},
            "reef": {"colonies": 83055,
                     "source": "USGS SQUID-5 survey, standing objects in the 1 cm DEM"}}


def test_a_count_that_came_out_of_a_survey_is_not_chosen():
    tool = _tool()
    rows = {r["what"]: r for r in tool.about(_a_place_built_before_cover(), None)}
    count = rows["How many colonies"]
    assert count["kind"] == tool.MEASURED, count


def test_no_row_is_tagged_chosen_while_its_source_names_a_survey():
    """The class of the bug, rather than the instance: whatever the tag is,
    the words beside it must not contradict it."""
    tool = _tool()
    for site in (_surveyed(), _a_place_built_before_cover()):
        for row in tool.about(site, None):
            if row["kind"] != tool.CHOSEN:
                continue
            said = (row["from"] or "").lower()
            assert not any(word in said for word in SURVEY_WORDS), row


def test_a_count_nobody_sourced_is_chosen_and_says_nothing():
    tool = _tool()
    bare = {"name": "x", "from": {}, "reef": {"colonies": 1000}}
    count = next(r for r in tool.about(bare, None) if r["what"] == "How many colonies")
    assert count["kind"] == tool.CHOSEN and count["from"] == ""


GUESS_WORDS = ("inferred", "assumed", "estimated", "chosen", "by construction",
               "stands in", "nobody")


def test_no_row_is_tagged_measured_while_its_words_say_otherwise():
    """The mirror of the test above, and the shape the fault took the
    first time: a row tagged measured whose value read "inferred from
    slope and relief"."""
    tool = _tool()
    for site in (_surveyed(), _a_place_built_before_cover()):
        for row in tool.about(site, None):
            if row["kind"] != tool.MEASURED:
                continue
            said = ((row["value"] or "") + " " + (row["from"] or "")).lower()
            assert not any(word in said for word in GUESS_WORDS), row


def test_the_same_holds_for_a_dive_s_conditions():
    """A dive's page has the same three fields and the same way to get
    them out of step."""
    tool = _tool()
    rows = tool.about_dive(FLOWN["cameFrom"], FLOWN["were"])
    for row in rows:
        said = (row["from"] or "").lower()
        if row["kind"] == tool.MEASURED:
            assert "nobody said" not in said, row
        if row["kind"] == tool.ASSUMED:
            assert "instrument" not in said and "buoy" not in said, row


# ── the heightfield note is a contract between two tools ─────────────────────
# tools/ground merges a survey DEM into bathymetry and writes a note beside
# the square; make-site reads that note straight into the place's provenance.
# The two agreed on nothing: ground wrote "surveyFraction" and make-site read
# "surveyedFraction", and neither wrote the survey names at all. A rebuilt
# Looe Key therefore claimed surveyed ground and named no survey for it, which
# is the precise shape of a laundered measurement.

def _source(name):
    import pathlib
    return (pathlib.Path(__file__).parent / name).read_text()


def _keys_make_site_reads_off_the_note():
    """The keys make-site pulls from the heights note into site['from']."""
    import re
    said = _source("make-site")
    return {m for m in re.findall(r'survey_note\.get\("([A-Za-z]+)"', said)}


def test_ground_writes_every_key_make_site_reads():
    wanted = _keys_make_site_reads_off_the_note()
    assert wanted, "make-site stopped reading the note; this test is stale"
    written = _source("ground").split('seabed_1m.json")')[1]
    written = written.split("# ── habitat")[0]
    for key in sorted(wanted):
        assert f'"{key}"' in written, (
            f"tools/ground does not write {key!r}, so a place rebuilt from its "
            f"heights loses it. make-site reads it off the note.")


def test_the_note_names_the_survey_it_merged():
    """A fraction without a name is not provenance: 11.5% of what?"""
    written = _source("ground")
    assert "dem_name" in written, "the merged DEM's name is never captured"
    put = written.split('seabed_1m.json")')[1].split("# ── habitat")[0]
    assert "dem_name" in put, "the name is captured and then not written down"
