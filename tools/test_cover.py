"""One definition of cover, used by everything that computes it.

There were two, and they disagreed by up to half as much again with nothing
broken: `tools/reef.py` took the median of *one-metre* cells clipped at one,
`tools/deliver` took a saturated mean over a different denominator. Two
statistics of two binnings wearing the same word.
"""

import importlib.machinery
import importlib.util
import math
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
import reef  # noqa: E402


def test_a_colony_is_spread_over_the_cells_it_actually_covers():
    """Not dropped in the cell its centre is in. A three-metre table put seven
    square metres into one one-metre cell and six of them were lost to the
    clip, while the neighbours it is physically standing over got nothing."""
    cell = reef.COVER_CELL_M
    # One four-square-metre colony sitting exactly on a cell corner, so it
    # must be quartered between four cells.
    on_a_corner = reef.cover_over([0.0], [0.0], [4.0], 100.0, cell)
    # And the same colony in the middle of a cell.
    inside = reef.cover_over([cell / 2, ], [cell / 2], [4.0], 100.0, cell)
    assert on_a_corner["reefGroundM2"] == pytest.approx(4 * cell * cell)
    assert inside["reefGroundM2"] == pytest.approx(cell * cell)
    # The colony area is the same either way: nothing is lost to a boundary.
    assert on_a_corner["colonyAreaM2"] == pytest.approx(4.0)
    assert inside["colonyAreaM2"] == pytest.approx(4.0)


def test_nothing_is_lost_at_a_cell_boundary():
    """The area that goes into the grid must be the area that came in,
    wherever the colonies land."""
    rng = np.random.default_rng(3)
    across, n = 200.0, 4000
    x = rng.uniform(-across / 2, across / 2, n)
    y = rng.uniform(-across / 2, across / 2, n)
    area = rng.uniform(0.05, 2.0, n)
    said = reef.cover_over(x, y, area, across)
    assert said["colonyAreaM2"] == pytest.approx(area.sum())
    # And the area actually placed into reef cells is nearly all of it: the
    # only losses are colonies clipped at the site edge.
    placed = said["piledUp"] * said["reefGroundM2"]
    assert placed > 0.97 * area.sum(), (placed, area.sum())


def test_cover_saturates_and_cannot_exceed_one():
    """Colonies are scattered rather than tiled, so area A over ground G
    covers 1 - exp(-A/G). Red Sea once came out at 110.78 per cent."""
    cell = reef.COVER_CELL_M
    # Ten times as much colony as there is ground in one cell.
    said = reef.cover_over([cell / 2] * 40, [cell / 2] * 40,
                           [cell * cell / 4] * 40, 100.0, cell)
    assert said["cover"] < 1.0
    assert said["cover"] > 0.99
    assert said["piledUp"] > 9.0


def test_an_empty_reef_is_not_a_division_by_zero():
    said = reef.cover_over([], [], [], 100.0)
    assert said["cover"] == 0.0 and said["reefGroundM2"] == 0.0


def test_thicket_is_a_share_of_the_reef_and_not_of_the_site():
    cell = reef.COVER_CELL_M
    # Two cells: one packed, one barely occupied.
    said = reef.cover_over([-cell * 4 + cell / 2, cell * 4 + cell / 2],
                           [cell / 2, cell / 2],
                           [cell * cell, 0.6], 100.0, cell)
    assert said["thicketM2"] == pytest.approx(cell * cell)
    assert said["reefGroundM2"] == pytest.approx(2 * cell * cell)


def test_everything_that_measures_cover_calls_the_one_function():
    """Three tools compute this and there must not be three definitions."""
    for name in ("reef.py", "reef-survey", "deliver"):
        source = (HERE / name).read_text()
        assert "cover_over(" in source, name
    # And `deliver` does not compute one of its own at all: it had two
    # denominators and its own saturation before it had none.
    given = (HERE / "deliver").read_text()
    assert "def cover_raster" not in given
    # And none of them keeps a private saturation of its own: the
    # `1 - exp(-A/G)` belongs in one place, and a second copy is how the two
    # definitions came to exist in the first place. Matched on the call and
    # not on the formula, because all three of them *describe* it in prose and
    # describing it is the opposite of the problem.
    for name in ("reef-survey", "deliver"):
        source = (HERE / name).read_text()
        assert "np.exp(-" not in source, f"{name} saturates cover itself"


def test_the_check_is_on_colony_area_and_not_on_cover():
    """Cover has a two-per-cent threshold in it and a threshold is a knife
    edge: on a sparse reef hundreds of cells sit within a rounding of it and
    flip between two computations that agree about every colony. At Al Fahal
    968 cells of 79,000 flipped and the covers came out 1.3 per cent apart
    with nothing wrong. Total colony area has no threshold in it and matched
    to one part in a million on every place."""
    source = (HERE / "deliver").read_text()
    assert "AGREES_WITHIN = 1e-4" in source
    assert 'abs(made["colonyAreaM2"] - built)' in source


def test_a_threshold_flips_cells_and_the_area_does_not():
    """The arithmetic of that, so it cannot be mistaken for a fault again."""
    cell = reef.COVER_CELL_M
    ground = cell * cell
    # A cell sitting exactly on the floor, and the same cell a hair under.
    just_over = ground * -math.log(1.0 - (reef.COVER_FLOOR + 1e-6))
    just_under = ground * -math.log(1.0 - (reef.COVER_FLOOR - 1e-6))
    over = reef.cover_over([cell / 2], [cell / 2], [just_over], 100.0, cell)
    under = reef.cover_over([cell / 2], [cell / 2], [just_under], 100.0, cell)
    # A hair of area moves the ground by a whole cell.
    assert over["reefGroundM2"] == pytest.approx(ground)
    assert under["reefGroundM2"] == 0.0
    # And the colony area barely moves at all.
    assert under["colonyAreaM2"] == pytest.approx(over["colonyAreaM2"], rel=1e-3)
