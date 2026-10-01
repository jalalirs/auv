"""The doubts an agent can name are the doubts the app offers.

Two catalogues of one thing, in two languages, held together by their keys: a
doubt the Sweeps screen offers that an agent cannot name, or the other way
round, is two products pretending to be one.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from coral_city_mcp import doubts

APP = (pathlib.Path(__file__).resolve().parents[3]
       / "apps/client/src/renderer/catalog/doubts.ts")


def _the_app_s():
    said = APP.read_text()
    found: dict[str, set[str]] = {}
    for block in re.split(r'\n\s*\{\s*\n\s*key: "', said)[1:]:
        dimension = block.split('"', 1)[0]
        found[dimension] = set(re.findall(r'\{ key: "([^"]+)"', block))
    return found


def test_every_doubt_the_app_offers_an_agent_can_name():
    app = _the_app_s()
    assert app, "could not read the app's catalogue; this test is stale"
    assert set(app) == set(doubts.DOUBTS), (set(app) ^ set(doubts.DOUBTS))
    for dimension, settings in app.items():
        assert settings == set(doubts.DOUBTS[dimension]["settings"]), dimension


def test_a_name_it_does_not_know_is_refused_not_dropped():
    """A sweep that quietly drops "thirty metres off" answers a smaller
    question than the one asked."""
    with pytest.raises(KeyError):
        doubts.asked({"the mooring": ["as drawn", "forty metres off"]})
    with pytest.raises(KeyError):
        doubts.asked({"the tide": ["high"]})


def test_it_counts_every_combination():
    assert doubts.scenarios({"current": ["still", "one knot"],
                             "the mooring": ["as drawn", "ten metres off",
                                             "thirty metres off"]}) == 6


def test_it_hands_over_the_contract_s_shape():
    said = doubts.asked({"current": ["one knot"]})
    assert said == {"current": {"one knot": {"currentMetresPerSecond": 0.51,
                                             "currentHeadingDeg": 30}}}
