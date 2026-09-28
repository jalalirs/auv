"""The rule the whole server exists to keep: no naked numbers.

Called test_marking rather than test_provenance because tools/ has a
test_provenance.py of its own, and pytest names a test module by its
basename: two files of one name in one run collide and the second never
gets collected. Which means the whole suite could not be run in one
command — the sort of thing that is discovered by a green tick on half
of it.

An assistant asked for a number will produce one. The risk of putting one
between an operator and a decision is that nothing in the loop knows which
numbers were measured — and the answer this platform can give, which a wrapper
around a simulator cannot, is that its transport will not carry a bare figure.

So it is tested as a property of the answers rather than checked by hand.
"""

from __future__ import annotations

import pytest

from coral_city_mcp import provenance as s


def test_a_value_needs_a_kind_we_recognise():
    with pytest.raises(ValueError):
        s.said(19.11, "probably", "the Atlas")


def test_a_value_needs_somebody_to_blame():
    """A measured value with no instrument named is the laundered measurement
    this platform exists to refuse. Cheaper to refuse here than to find it in
    somebody's report."""
    for empty in ("", "   ", None):
        with pytest.raises(ValueError):
            s.said(2.0, s.MEASURED, empty)


def test_unknown_is_not_zero_and_not_null():
    """A bench row written before the water was a field did not fly in still
    water. Nobody wrote down what it flew in."""
    said = s.unknown("nobody recorded the water")
    assert said["value"] is None
    assert said["kind"] is None
    assert "nobody recorded" in said["unknown"]


def test_numbers_finds_a_bare_figure_anywhere_in_a_tree():
    clean = {"a": s.said(1.0, s.MEASURED, "a ruler"),
             "b": [s.said(2, s.DERIVED, "arithmetic")],
             "c": {"d": s.said(3, s.CHOSEN, "somebody picked it")}}
    assert s.numbers(clean) == []
    leaky = dict(clean, rmsAfterM=2.0)
    assert s.numbers(leaky) == ["rmsAfterM"]
    deep = {"fit": {"bands": [{"medianM": -16.35}]}}
    assert s.numbers(deep) == ["fit.bands[0].medianM"]


def test_a_bool_is_not_a_number():
    """`published: true` is not a figure anybody can misreport as measured."""
    assert s.numbers({"published": True, "flyable": False}) == []


def test_the_four_words_are_the_platform_s_own():
    assert set(s.KINDS) == {"measured", "derived", "chosen", "assumed"}
