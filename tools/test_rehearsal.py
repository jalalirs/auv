"""A sweep's answer, as a page somebody can send.

The answer is on a screen in the application, which is the right place for
whoever ran the sweep and the wrong place for whoever decides whether the
boat goes out. That person will not open the application.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader("rehearsal", str(HERE / "rehearsal"))
    spec = importlib.util.spec_from_loader("rehearsal", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


FOUND = {
    "scenarios": 8, "flown": 8, "flownRuns": 24, "flying": 0, "survived": 5,
    "marginal": 1, "repeats": 3, "good": 0.8, "heldBack": 0,
    "physics": [2],
    "turnsOn": "one knot of current",
    "failsOf": [3, 4],
    "rescue": "a two metre allowance",
    "rescueOf": [2, 3],
    "matters": [
        {"name": "current", "changes": 0.62, "onACoinFlip": False,
         "rates": [{"value": "still", "survived": 4, "of": 4, "failedShare": 0.0},
                   {"value": "one knot", "survived": 1, "of": 4, "failedShare": 0.75}]},
        {"name": "visibility", "changes": 0.25, "onACoinFlip": True,
         "rates": [{"value": "clear", "survived": 3, "of": 4, "failedShare": 0.25},
                   {"value": "murky", "survived": 2, "of": 4, "failedShare": 0.5}]},
    ],
    "madeNoDifference": ["the mooring's position"],
    "cost": {"runs": 24, "survived": 15, "diveEnergyWh": 180.0, "diveHours": 1.4,
             "workingShare": 0.62, "perCharge": 2.3, "workingDayHours": 10.0,
             "perDay": 2.0, "heldBackBy": "the battery", "survives": 0.625,
             "shipDaysPerWorkingDay": 1.6},
    "scenariosFlown": [
        {"label": "still · clear", "runs": 3, "survivedRuns": 3, "survived": True,
         "marginal": False, "score": 0.94},
        {"label": "one knot · murky", "runs": 3, "survivedRuns": 1, "survived": False,
         "marginal": False, "score": 0.31},
        {"label": "one knot · clear", "runs": 3, "survivedRuns": 2, "survived": True,
         "marginal": True, "score": 0.81},
    ],
}


def test_it_says_what_the_day_turns_on():
    page = _tool().page("Al Fahal transect", FOUND)
    assert "It turns on one knot of current" in page
    assert "3 of 4 scenarios with it fail" in page
    assert "rescued by a two metre allowance" in page


def test_a_doubt_that_rests_on_coin_flips_is_named_and_not_trusted():
    """The most expensive mistake a rehearsal can make is sending somebody to
    worry about the wrong thing."""
    page = _tool().page("x", FOUND)
    assert "where the coins landed" in page
    assert "Named, not ranked" in page


def test_what_made_no_difference_is_said_once_and_not_ranked():
    page = _tool().page("x", FOUND)
    assert "Made no difference: the mooring&#x27;s position" in page
    # Not given a bar and a percentage of its own.
    assert page.count("the mooring") == 1


def test_mixed_physics_is_a_warning_at_the_top_and_not_an_average():
    page = _tool().page("x", {**FOUND, "physics": [1, 2]})
    assert "not all computed by the same simulator" in page
    assert page.index("not all computed") < page.index("What changes the outcome")


def test_a_scenario_that_could_have_gone_either_way_says_so():
    page = _tool().page("x", FOUND)
    assert "either way" in page


def test_the_cost_says_what_holds_the_day_back():
    """A job held back by the battery is fixed by a second battery; a job
    held back by the clock is not."""
    page = _tool().page("x", FOUND)
    assert "held back by the battery" in page
    assert "1.6 ship days for one working day" in page


def test_a_sweep_that_nothing_breaks_says_that_instead():
    page = _tool().page("x", {**FOUND, "survived": 8, "turnsOn": ""})
    assert "Nothing in the doubt list breaks it" in page


def test_the_page_needs_nothing_to_render():
    page = _tool().page("x", FOUND)
    for fetched in ("<script", "@import", "<link", "src=", 'href="http'):
        assert fetched not in page, fetched
    assert page.startswith("<!doctype html>")
    assert "-apple-system" in page, "it printed without the house stylesheet"


def test_a_sweep_with_nothing_flown_is_refused(tmp_path, capsys):
    tool = _tool()
    empty = tmp_path / "findings.json"
    empty.write_text(json.dumps({"scenarios": 8, "flown": 0}))
    tool.sys.argv = ["rehearsal", str(empty)]
    assert tool.main() == 1
    assert not (tmp_path / "findings.html").exists()


def test_it_writes_the_page_beside_the_findings(tmp_path):
    tool = _tool()
    where = tmp_path / "findings.json"
    where.write_text(json.dumps(FOUND))
    tool.sys.argv = ["rehearsal", str(where), "--name", "Al Fahal transect"]
    assert tool.main() == 0
    assert "Al Fahal transect" in (tmp_path / "findings.html").read_text()


def test_the_article_is_not_doubled():
    """The platform says "the clock" and "the battery", article and all.
    The first real sweep this was pointed at read "held back by the the
    clock"."""
    tool = _tool()
    page = tool.page("x", {**FOUND, "cost": {**FOUND["cost"],
                                             "heldBackBy": "the clock"}})
    assert "the the" not in page
    assert "held back by the clock" in page
