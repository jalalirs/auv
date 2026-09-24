"""A paper in the reference, kept apart from a fetch."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import tempfile

_loader = importlib.machinery.SourceFileLoader(
    "cite", str(pathlib.Path(__file__).resolve().parent / "cite"))
_spec = importlib.util.spec_from_loader("cite", _loader)
cite = importlib.util.module_from_spec(_spec)
_loader.exec_module(cite)


def test_a_citation_says_it_was_not_fetched():
    """The distinction the whole tool exists for: a number read out of a paper
    is not a number somebody's API returned."""
    into = pathlib.Path(tempfile.mkdtemp())
    cite.cite(into, "benthos", "Somebody et al. 2017", {"porites": 34.6})
    got = json.loads((into / "benthos.json").read_text())
    assert got["fetched"] is False
    assert got["says"] == {"porites": 34.6}


def test_it_lands_beside_the_fetched_sources_and_not_instead_of_them():
    into = pathlib.Path(tempfile.mkdtemp())
    (into / "reference.json").write_text(json.dumps(
        {"name": "somewhere", "sources": {"photographs": {"file": "p.json"}}}))
    cite.cite(into, "benthos", "Somebody et al. 2017", {"a": 1}, doi="10.x/y")
    whole = json.loads((into / "reference.json").read_text())
    assert set(whole["sources"]) == {"photographs", "benthos"}
    assert whole["sources"]["benthos"]["licence"] == "cited, not fetched"
    assert whole["sources"]["benthos"]["doi"] == "10.x/y"


def test_it_makes_a_reference_when_there_is_none():
    into = pathlib.Path(tempfile.mkdtemp()) / "fresh"
    cite.cite(into, "benthos", "Somebody 2020", {"a": 1})
    whole = json.loads((into / "reference.json").read_text())
    assert whole["name"] == "fresh"
    assert "benthos" in whole["sources"]


def test_the_numbers_are_kept_not_a_sentence_about_them():
    """So a later reader can hold the model against them."""
    into = pathlib.Path(tempfile.mkdtemp())
    numbers = {"porites": 34.6, "pocillopora": 22.8, "acropora": 6.4}
    cite.cite(into, "benthos", "Somebody 2024", numbers)
    assert json.loads((into / "benthos.json").read_text())["says"] == numbers
