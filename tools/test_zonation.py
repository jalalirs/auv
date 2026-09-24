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


def test_hawaii_has_no_tables_at_all():
    """The main Hawaiian islands have essentially no Acropora. A table is the
    shape a Red Sea slope is known for and it does not occur here — which is
    the thing a diver would notice first in a wrong picture."""
    for _, weights, _ in zonation.bands_for("hawaii"):
        assert weights.get("table", 0.0) == 0.0, weights


def test_hawaii_is_carried_by_finger_and_encrusting():
    """Porites compressa and Montipora capitata are the two most abundant
    species in Kāne'ohe Bay, and they are those two shapes."""
    mix = dict(zonation.bands_for("hawaii")[1][1])
    total = sum(mix.values())
    assert (mix["finger"] + mix["encrusting"]) / total > 0.5, mix


def test_no_shallow_gorgonian_fans_outside_the_caribbean():
    for name in ("hawaii", "red-sea"):
        shallow = dict(zonation.bands_for(name)[0][1])
        assert shallow.get("fan", 0.0) == 0.0, (name, shallow)
    assert dict(zonation.bands_for("caribbean")[1][1]).get("fan", 0.0) > 0.0


def test_the_three_reefs_are_actually_different():
    """Three names for one mix would be worse than one name, because it would
    look like somebody had checked."""
    seen = set()
    for name in zonation.ASSEMBLAGES:
        mix = zonation.bands_for(name)
        key = tuple(tuple(sorted(w.items())) for _, w, _ in mix)
        assert key not in seen, name
        seen.add(key)
