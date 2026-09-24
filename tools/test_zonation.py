"""Which reef a place is drawn as.

The shapes are the same in every ocean and the mix is not. Everything on this
platform was grown from one mix read off Caribbean and Red Sea surveys
together, which came out heavy in gorgonian fans — a Caribbean signature the
Red Sea does not have. Al Fahal is where sixty-seven of sixty-eight dives
happen, and it was being drawn as a Caribbean reef.
"""

from __future__ import annotations

import numpy as np
import pytest

import zonation


def test_both_reefs_draw_from_one_palette():
    """A reef's prototypes are built from the whole palette, so the weights of
    whichever mix it was grown from have to line up with it."""
    kinds, _, _ = zonation.community(
        np.array([5.0]), np.random.default_rng(0), zonation.bands_for("red-sea"))
    other, _, _ = zonation.community(
        np.array([5.0]), np.random.default_rng(0), zonation.bands_for("caribbean"))
    assert kinds == other


def test_the_red_sea_is_tables_where_the_caribbean_is_fans():
    """The one difference that shows in a frame."""

    def share(mix, kind, depth):
        for deepest, weights, _ in mix:
            if depth <= deepest:
                return weights.get(kind, 0.0) / sum(weights.values())
        return 0.0

    for depth in (10.0, 18.0, 26.0):
        assert share(zonation.bands_for("red-sea"), "fan", depth) < \
            share(zonation.bands_for("caribbean"), "fan", depth), depth
        assert share(zonation.bands_for("red-sea"), "table", depth) > \
            share(zonation.bands_for("caribbean"), "table", depth), depth


def test_the_red_sea_is_carried_by_massives_and_branching():
    """Porites and Pocillopora are a third and a fifth of the coral cover on
    Al Fahal. On the upper fore reef they have to be most of what is drawn."""
    mix = dict(zonation.bands_for("red-sea")[1][1])
    total = sum(mix.values())
    assert (mix["massive"] + mix["branching"]) / total > 0.45, mix


def test_an_unknown_reef_says_so_rather_than_guessing():
    with pytest.raises(KeyError, match="no assemblage"):
        zonation.bands_for("mediterranean")


def test_naming_nothing_keeps_what_the_platform_had():
    assert zonation.bands_for(None) is zonation.BANDS


def test_every_band_is_a_mix_that_sums_to_something():
    for name, mix in zonation.ASSEMBLAGES.items():
        deepest = [edge for edge, _, _ in mix]
        assert deepest == sorted(deepest), name
        for _, weights, cap in mix:
            assert sum(weights.values()) > 0.0, name
            assert cap > 0.0, name
