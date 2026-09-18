"""Lines bow with the current, and a chart does not say where they are.

A line drawn on a chart is where somebody put its two ends. Where it actually
*is* is somewhere else, and by metres rather than centimetres — which is the
whole reason a rehearsal needs it: a vehicle flying under a mooring line at the
depth the chart implies meets it at a different depth entirely, and in a
current it may not be anywhere near where it was drawn.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from world import World


def a_line(slack: float = 0.1, weight: float = 0.0) -> World:
    """A hundred metres between two blocks twenty metres down."""
    return World({"things": [{
        "id": "line", "kind": "mooring-line", "slack": slack,
        "weightNPerM": weight, "radiusM": 0.05,
        "ends": [{"x": -50.0, "y": 0.0, "z": -20.0},
                 {"x": 50.0, "y": 0.0, "z": -20.0}]}]})


def arc(curve) -> float:
    return sum(float(np.linalg.norm(np.asarray(b) - np.asarray(a)))
               for a, b in zip(curve, curve[1:]))


def across(curve) -> float:
    return max(abs(float(one[1])) for one in curve)


def lowest(curve) -> float:
    return -min(float(one[2]) for one in curve)


def test_still_water_leaves_the_catenary_alone():
    world = a_line()
    world.in_this_water(np.zeros(3))
    curve = world.things[0].curve
    # Ten per cent of slack over a hundred metres hangs about twenty below.
    assert 38.0 < lowest(curve) < 42.0, f"{lowest(curve):.1f} m"
    assert across(curve) < 0.5, "nothing pushed it anywhere"
    assert world.things[0].leaned_by == 0.0


def test_a_current_moves_a_line_by_metres():
    """Not centimetres. This is the size of the thing a chart does not say."""
    world = a_line(weight=1.0)
    world.in_this_water(np.array([0.0, 0.4, 0.0]))
    one = world.things[0]
    assert one.leaned_by > 10.0, f"it only moved {one.leaned_by:.1f} m"
    assert across(one.curve) > 15.0, f"it only went {across(one.curve):.1f} m across"
    # And it is no longer hanging where the still-water catenary put it.
    assert lowest(one.curve) < 35.0, f"still hanging to {lowest(one.curve):.1f} m"


def test_a_heavier_line_leans_further_the_faster_the_water_goes():
    moved = []
    for speed in (0.1, 0.2, 0.4):
        world = a_line(weight=1.0)
        world.in_this_water(np.array([0.0, speed, 0.0]))
        moved.append(world.things[0].leaned_by)
    assert moved[0] < moved[1] < moved[2], moved


def test_a_weightless_line_takes_one_shape_whatever_the_speed():
    """Which is true and looks like a bug until it is thought about.

    With no weight in it, scaling the drag scales every tension by the same
    amount and leaves the shape alone: a limp line in a fast current is the
    same curve as a limp line in a slow one, pulled harder. A line that hangs
    is the one whose shape the speed decides, because there the speed is
    changing the ratio of two different forces.
    """
    shapes = []
    for speed in (0.2, 0.8):
        world = a_line(weight=0.0)
        world.in_this_water(np.array([0.0, speed, 0.0]))
        shapes.append(np.array([np.asarray(one) for one in world.things[0].curve]))
    assert float(np.max(np.abs(shapes[0] - shapes[1]))) < 0.5, "the shape moved with the speed"


def test_a_line_keeps_its_length():
    """A cable being stretched by its own solver is not a cable.

    The position-based constraint has to be swept along the whole chain or the
    drag pushes faster than it can pull back: a hundred-metre span with ten
    metres of slack settled at a hundred and thirty-five metres of arc before
    this was fixed.
    """
    for speed in (0.0, 0.2, 0.4, 0.8):
        world = a_line(weight=1.0)
        world.in_this_water(np.array([0.0, speed, 0.0]))
        got = arc(world.things[0].curve)
        assert 108.0 < got < 114.0, f"at {speed} m/s the line is {got:.1f} m long, not 110"


def test_a_vehicle_meets_the_line_where_it_is_and_not_where_it_was_drawn():
    """The point of the whole thing.

    Mid-span, at the depth the still-water catenary puts the line, in a current
    that has taken it somewhere else: the chart says you would hit it and you
    do not, and where you would hit it now is nowhere the chart mentions.
    """
    world = a_line(weight=1.0)
    hanging = np.array([0.0, 0.0, -float(lowest(world.things[0].curve))])
    assert world.things[0].near(hanging, 0.3), "it hangs there in still water"
    world.in_this_water(np.array([0.0, 0.4, 0.0]))
    assert not world.things[0].near(hanging, 0.3), "and the current moved it"
    # Where it is now, which is somewhere across the flow.
    moved = max(world.things[0].curve, key=lambda one: abs(float(one[1])))
    assert world.things[0].near(moved, 0.3)
