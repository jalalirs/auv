"""Where a plan of work puts the vehicle in the water.

Until this, the place chose — by coral cover, out of a number its own survey
later disproved. A mission could not say "we launch from the ship" with a ship
drawn on the layout, and the transit out to the work and back was neither flown
nor counted in what the day costs.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from world import World  # noqa: E402


class Placed:
    """The part of a dive that a launch point touches, and nothing else."""

    def __init__(self, world, water_level=0.0, floor=-20.0):
        self.world = world
        self.water_level = water_level
        self.floor = floor
        self.seabed = None
        self.half_height = 0.2
        self.said = []

    def say(self, kind, **detail):
        self.said.append((kind, detail))

    # The method under test, borrowed rather than reimplemented.
    from runner import Dive as _Dive
    launch_from = _Dive.launch_from


def a_site():
    return World({"things": [
        {"id": "ship-1", "kind": "ship", "x": 100.0, "y": -40.0, "z": 0.0},
        {"id": "block-1", "kind": "mooring-block", "x": -60.0, "y": 20.0, "z": -18.0},
    ]})


def test_a_mission_launches_from_something_drawn():
    """The whole point: a ship on the layout is a place a dive can begin."""
    placed = Placed(a_site())
    where = placed.launch_from({"from": "ship-1"})
    assert where is not None, "it should launch from the ship"
    assert round(where[0]) == 100 and round(where[1]) == -40, where
    # And at the surface, because that is where a vehicle over the side is.
    assert where[2] > -1.0, f"a surface launch should be at the surface: {where}"


def test_a_launch_may_name_a_depth():
    """A vehicle lowered on a line does not start at the surface."""
    placed = Placed(a_site())
    where = placed.launch_from({"from": "ship-1", "depthM": 6.0})
    assert abs(where[2] + 6.0) < 0.01, where


def test_a_launch_may_be_a_point():
    """Nothing drawn is the right answer often enough to allow it."""
    placed = Placed(a_site())
    where = placed.launch_from({"at": [12.0, 34.0]})
    assert round(where[0]) == 12 and round(where[1]) == 34, where


def test_it_does_not_launch_into_the_seabed():
    """A ship moored in four metres does not put a vehicle into the sand."""
    placed = Placed(a_site(), floor=-4.0)
    placed.seabed = type("Flat", (), {"under": staticmethod(lambda x, y: -4.0)})()
    where = placed.launch_from({"from": "ship-1", "depthM": 30.0})
    assert where[2] > -4.0, f"asked for thirty metres in four: {where}"


def test_a_launch_point_that_is_not_there_says_so():
    """Rather than silently starting somewhere else.

    A mission naming a ship nobody drew is a mission somebody edited without
    the layout in front of them, and a dive that quietly began a kilometre away
    would be a dive whose transit and whose navigation error were both wrong
    with nothing in the record to say why.
    """
    placed = Placed(a_site())
    assert placed.launch_from({"from": "ship-that-sailed"}) is None
    assert any(kind == "launch_missing" for kind, _ in placed.said), placed.said


def test_no_launch_is_no_opinion():
    """A mission that does not say leaves the place to choose, as before."""
    placed = Placed(a_site())
    assert placed.launch_from(None) is None
    assert placed.launch_from({}) is None
