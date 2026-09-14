"""What is in the water besides the vehicle.

A place is a seabed and its coral, both read from a survey. That is the right
foundation and it is not a site: a dive happens in a site somebody *arranged*,
and an array laid in a particular pattern is not in any survey.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from world import World  # noqa: E402

ARRAY = {"describedBy": "coral-city/layout/v1", "things": [
    {"id": "t1", "kind": "transponder", "x": 0.0, "y": 0.0, "groundM": 14.0},
    {"id": "t2", "kind": "transponder", "x": 50.0, "y": 0.0, "groundM": 15.0},
    {"id": "frame", "kind": "nursery-frame", "x": 20.0, "y": -10.0, "groundM": 12.0},
]}


def test_a_place_with_no_arrangement_is_empty_and_costs_nothing():
    """Most dives are flown over bare ground and always will be."""
    empty = World(None)
    assert len(empty) == 0
    where = np.array([0.0, 0.0, -14.0])
    allowed, struck = empty.keep_out(where, where, 0.15)
    assert struck is None and allowed is where


def test_a_thing_sits_where_its_landing_rule_put_it():
    """Resolved when it was drawn, against that seabed — which is why a layout
    belongs to a place and is wrong anywhere else."""
    world = World(ARRAY)
    assert len(world) == 3
    assert world.by_id("t1").at[2] == -14.0
    assert world.by_id("t2").at[2] == -15.0
    assert [t.id for t in world.of_kind("transponder")] == ["t1", "t2"]


def test_a_vehicle_driven_at_a_thing_stops():
    world = World(ARRAY)
    frame = world.by_id("frame")
    # Straight into the middle of the nursery frame, from the west.
    inside = np.array([20.0, -10.0, -11.6])
    came_from = np.array([17.0, -10.0, -11.6])
    allowed, struck = world.keep_out(inside, came_from, 0.15)
    assert struck is not None and struck.id == "frame"
    away = float(np.hypot(allowed[0] - frame.at[0], allowed[1] - frame.at[1]))
    assert away >= frame.radius, "it is put back outside the thing"
    assert allowed[0] < frame.at[0], "and out the way it came in, not through"


def test_it_goes_back_the_way_it_came_rather_than_round():
    """Pushing to the nearest face would slide a vehicle round something it
    drove straight at, which is a vehicle passing through it slowly."""
    world = World(ARRAY)
    frame = world.by_id("frame")
    approaching = np.array([20.5, -10.0, -11.6])      # just past the middle, from the east
    came_from = np.array([24.0, -10.0, -11.6])
    allowed, _ = world.keep_out(approaching, came_from, 0.15)
    assert allowed[0] > frame.at[0], "east of it, where it came from"


def test_something_above_or_below_a_thing_is_not_in_it():
    """A transponder is two metres tall and a vehicle at forty is not in it."""
    world = World(ARRAY)
    over = np.array([0.0, 0.0, -5.0])
    allowed, struck = world.keep_out(over, over, 0.15)
    assert struck is None
    under = np.array([0.0, 0.0, -30.0])
    assert world.keep_out(under, under, 0.15)[1] is None


def test_it_says_what_is_in_the_water():
    world = World(ARRAY)
    said = world.described()
    assert said["things"] == 3
    assert said["of"] == {"transponder": 2, "nursery-frame": 1}
    assert said["struck"] == 0
