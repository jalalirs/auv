"""What is in the water besides the vehicle.

A place is a seabed and its coral, both read from a survey. That is the right
foundation and it is not a site: a dive happens in a site somebody *arranged*,
and an array laid in a particular pattern is not in any survey.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from world import KINDS, World

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


# ── the rest of the palette ──────────────────────────────────────────────────

def test_a_ship_hangs_below_the_surface_not_above_it():
    """Three metres of hull in the water, not three metres of sky.

    A ship whose extent went upward would be something a vehicle at two metres
    deep flew straight through, and the draught — the only part of a ship that
    is in the sea — would obstruct nothing.
    """
    world = World({"things": [{"id": "s", "kind": "ship", "x": 0.0, "y": 0.0}]})
    ship = world.things[0]
    assert ship.near([0.0, 0.0, -2.0]), "two metres down is inside the hull"
    assert not ship.near([0.0, 0.0, 2.0]), "two metres up is the air above it"
    assert not ship.near([0.0, 0.0, -5.0]), "five metres down is under the keel"


def test_a_line_hangs_where_the_slack_puts_it():
    """A slack line is not where the straight line between its ends is.

    Two blocks a hundred metres apart on a flat twenty-metre bottom, joined by
    a line five per cent longer than the gap. Straight, it would sit at twenty
    metres all the way across. Hanging, its middle is metres lower — and a
    vehicle flying the straight line's depth at mid-span meets it.
    """
    world = World({"things": [{
        "id": "line", "kind": "mooring-line", "slack": 0.05,
        "ends": [{"x": -50.0, "y": 0.0, "z": -20.0},
                 {"x": 50.0, "y": 0.0, "z": -20.0}]}]})
    line = world.things[0]
    lowest = min(float(p[2]) for p in line.curve)
    assert lowest < -23.0, f"five per cent of slack over a hundred metres sags; got {lowest:.1f}"
    assert not line.near([0.0, 0.0, -20.0], 0.2), "the middle is no longer up there"
    assert line.near([0.0, 0.0, lowest], 0.2), "it is down where it hangs"


def test_a_taut_line_is_a_straight_one():
    world = World({"things": [{
        "id": "riser", "kind": "mooring-line",
        "ends": [{"x": 0.0, "y": 0.0, "z": -30.0}, {"x": 0.0, "y": 0.0, "z": 0.0}]}]})
    riser = world.things[0]
    assert riser.near([0.0, 0.0, -15.0], 0.2), "a riser is in the way all the way up"
    assert not riser.near([3.0, 0.0, -15.0], 0.2)


def test_a_vehicle_driven_at_a_line_is_stopped_by_it():
    world = World({"things": [{
        "id": "riser", "kind": "mooring-line", "radiusM": 0.1,
        "ends": [{"x": 0.0, "y": 0.0, "z": -30.0}, {"x": 0.0, "y": 0.0, "z": 0.0}]}]})
    allowed, struck = world.keep_out(np.array([0.0, 0.0, -15.0]),
                                     np.array([-2.0, 0.0, -15.0]), 0.3)
    assert struck is not None and struck.kind == "mooring-line"
    assert float(np.hypot(allowed[0], allowed[1])) >= 0.39, "put back outside it"
    assert allowed[0] < 0, "back the way it came, not through to the far side"


def test_a_plot_is_something_to_point_at_not_something_to_hit():
    """A boundary drawn on a chart is not in the water.

    A vehicle that bounced off a restoration cell would be a vehicle bouncing
    off a line on a map. What a plot is for is being pointed at: inside it or
    not, which is what scoring "plant twenty inside this cell" needs.
    """
    world = World({"things": [{
        "id": "cell", "kind": "restoration-cell",
        "corners": [{"x": 0.0, "y": 0.0}, {"x": 40.0, "y": 0.0},
                    {"x": 40.0, "y": 30.0}, {"x": 0.0, "y": 30.0}]}]})
    cell = world.things[0]
    assert cell.area_m2() == 1200.0
    assert cell.contains([20.0, 15.0, -9.0])
    assert not cell.contains([50.0, 15.0, -9.0])
    allowed, struck = world.keep_out(np.array([20.0, 15.0, -9.0]),
                                     np.array([19.0, 15.0, -9.0]), 0.3)
    assert struck is None, "you fly through a plot, you do not hit it"
    assert [one.id for one in world.inside([20.0, 15.0, -9.0])] == ["cell"]


def test_every_kind_in_the_palette_builds_and_describes_itself():
    """The palette is a list somebody will add to, so the loop is the test."""
    drawn = {
        "transponder":   {"x": 1.0, "y": 2.0, "groundM": 14.0},
        "mooring-block": {"x": 1.0, "y": 2.0, "groundM": 14.0},
        "nursery-frame": {"x": 1.0, "y": 2.0, "groundM": 14.0},
        "marker-post":   {"x": 1.0, "y": 2.0, "groundM": 14.0},
        "buoy":          {"x": 1.0, "y": 2.0},
        "ship":          {"x": 1.0, "y": 2.0},
        "mooring-line":  {"ends": [{"x": 0.0, "y": 0.0, "groundM": 14.0},
                                   {"x": 1.0, "y": 2.0, "z": 0.0}]},
        "restoration-cell": {"corners": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0},
                                         {"x": 10.0, "y": 10.0}]},
    }
    assert set(drawn) == set(KINDS), "a kind in the palette nobody drew here"
    world = World({"things": [dict(said, id=kind, kind=kind)
                              for kind, said in drawn.items()]})
    assert len(world) == len(KINDS)
    for one in world.things:
        assert one.described()["is"], f"{one.kind} says nothing about itself"
    counted = world.described()["of"]
    assert all(counted[kind] == 1 for kind in KINDS)
