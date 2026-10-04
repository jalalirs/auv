"""What an agent is told about a real place.

The fixture is Al Fahal's own site.json, copied off the box rather than written
here, because the thing being tested is whether this shapes a *real* record
honestly and a record I made up would agree with me.

Al Fahal is the right one to test on. Its seabed is Sentinel-2, uncalibrated,
fitted against 26,726 ICESat-2 photons to an rms of 2.00 m — and that figure is
the top five metres, because 22,430 of those photons sit there and below fifteen
the fit is sixteen metres out. An agent given the rms and not the depth it holds
to has been handed the exact number that reads as solved.
"""

from __future__ import annotations

import json
import pathlib

from iocean_mcp import provenance
from iocean_mcp import tools

HERE = pathlib.Path(__file__).resolve().parent
SITE = json.loads((HERE / "from-the-box" / "al-fahal.site.json").read_text())


class OnePlace:
    """Enough platform to answer places_get, with the real record behind it."""

    def places(self):
        return [{"id": "cty_1", "slug": "al-fahal", "name": "Al Fahal"}]

    def versions_of_place(self, place):
        return [{"id": "ver_1", "createdAt": "2026-09-28T00:00:00Z"}]

    def files(self, version):
        return [{"path": "site.json", "url": "file://site"}]


def _answer(monkeypatch):
    monkeypatch.setattr(tools, "_site_of", lambda platform, place: SITE)
    return tools.places_get(OnePlace(), "al-fahal")


def test_it_says_the_depth_the_fit_actually_holds_to(monkeypatch):
    said = _answer(monkeypatch)
    good_to = said["ground"]["calibratedToM"]
    assert good_to["value"] == 5.0
    assert good_to["kind"] == provenance.DERIVED
    assert "does not hold" in good_to["note"]


def test_a_fitted_seabed_is_derived_and_never_measured(monkeypatch):
    """A fit against a laser does not make a satellite a survey."""
    said = _answer(monkeypatch)
    assert said["ground"]["surveyed"]["value"] is False
    assert said["ground"]["fittedAgainst"]["kind"] == provenance.DERIVED
    assert said["ground"]["deepestM"]["kind"] == provenance.DERIVED


def test_the_water_is_measured_because_somebody_measured_it(monkeypatch):
    """Al Fahal carries Overmans & Agusti's Kd(PAR) from the KAUST pelagic
    station, which is its own water rather than a reading carried from
    elsewhere."""
    said = _answer(monkeypatch)
    assert said["water"]["value"] == "IB"
    assert said["water"]["kind"] == provenance.MEASURED
    assert "Overmans" in said["water"]["from"]


def test_not_one_bare_number_comes_back(monkeypatch):
    """The rule, over a whole real answer rather than a constructed one."""
    said = _answer(monkeypatch)
    assert provenance.numbers(said) == []


def test_every_marked_value_names_a_source(monkeypatch):
    said = _answer(monkeypatch)

    def walk(node):
        if isinstance(node, dict):
            if "kind" in node and "from" in node:
                if node["kind"] is not None:
                    assert node["from"], f"{node} is marked and blames nobody"
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(said)


def test_a_named_source_is_not_an_assumption(monkeypatch):
    """Al Fahal names a Copernicus scene and says plainly that it is
    satellite-derived and not a survey. That is a stated fact with a source.
    Assumed is for when nobody said."""
    said = _answer(monkeypatch)
    surveyed = said["ground"]["surveyed"]
    assert surveyed["kind"] == provenance.DERIVED
    assert "Sentinel-2" in surveyed["from"]
    assert surveyed["note"] == "derived, not surveyed"
