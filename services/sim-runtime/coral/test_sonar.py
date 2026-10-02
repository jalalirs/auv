"""What the vehicle can see that nobody told it about.

An imaging sonar has been declared in the BlueROV2's package since the
beginning and has returned nothing this whole time, because there was nothing
in the world to return off.
"""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sonar import Sonar
from world import World

FORWARD = np.eye(3)


def a_sonar(**more) -> Sonar:
    said = {"rangeM": [0.5, 10.0], "horizontalFovDeg": 130, "verticalFovDeg": 20,
            "position": [0.0, 0.0, 0.0], "missesShare": 0.0, "rangeNoiseM": 0.0}
    said.update(more)
    return Sonar(said, seed=3)


def test_empty_water_returns_nothing():
    one = a_sonar()
    one.ping(0.0, np.zeros(3), FORWARD, World(None), None)
    assert one.nearest() is None
    assert one.said()["returns"] == 0


def test_it_sees_a_block_ahead_and_says_how_far():
    world = World({"things": [{"id": "block", "kind": "mooring-block",
                               "x": 6.0, "y": 0.0, "z": -0.3}]})
    one = a_sonar()
    one.ping(0.0, np.zeros(3), FORWARD, world, None)
    near = one.nearest()
    assert near is not None, "it should have seen the block"
    # Six metres to the middle, eight tenths of a metre of radius off it.
    assert 5.0 < near["rangeM"] < 5.4, near
    assert abs(near["bearingRad"]) < math.radians(3), "it is dead ahead"


def test_it_does_not_see_what_is_behind_it():
    world = World({"things": [{"id": "block", "kind": "mooring-block",
                               "x": -6.0, "y": 0.0, "z": -0.3}]})
    one = a_sonar()
    one.ping(0.0, np.zeros(3), FORWARD, world, None)
    assert one.nearest() is None


def test_it_does_not_see_past_its_range():
    world = World({"things": [{"id": "block", "kind": "mooring-block",
                               "x": 40.0, "y": 0.0, "z": -0.3}]})
    one = a_sonar()
    one.ping(0.0, np.zeros(3), FORWARD, world, None)
    assert one.nearest() is None


def test_the_bearing_says_which_side_to_turn():
    """Positive to starboard, so "away from it" is a sign."""
    for y, side in ((4.0, "port"), (-4.0, "starboard")):
        world = World({"things": [{"id": "post", "kind": "marker-post",
                                   "x": 5.0, "y": y, "z": -1.5}]})
        one = a_sonar()
        one.ping(0.0, np.zeros(3), FORWARD, world, None)
        near = one.nearest()
        assert near is not None, f"it should see the {side} post"
        if side == "port":
            assert near["bearingRad"] > 0.2, near
        else:
            assert near["bearingRad"] < -0.2, near


def test_a_plot_on_the_chart_returns_nothing():
    """A boundary somebody drew is not a thing that returns sound."""
    world = World({"things": [{
        "id": "cell", "kind": "restoration-cell", "x": 5.0, "y": 0.0, "groundM": 9.0,
        "corners": [{"x": 0.0, "y": -10.0}, {"x": 10.0, "y": -10.0},
                    {"x": 10.0, "y": 10.0}, {"x": 0.0, "y": 10.0}]}]})
    one = a_sonar()
    one.ping(0.0, np.zeros(3), FORWARD, world, None)
    assert one.nearest() is None


def test_it_sees_a_line_across_its_path():
    """A mooring riser is millimetres thick and a sonar still finds it."""
    world = World({"things": [{
        "id": "riser", "kind": "mooring-line", "radiusM": 0.05,
        "ends": [{"x": 5.0, "y": 0.0, "z": -8.0}, {"x": 5.0, "y": 0.0, "z": 0.0}]}]})
    one = a_sonar()
    one.ping(0.0, np.array([0.0, 0.0, -4.0]), FORWARD, world, None)
    near = one.nearest()
    assert near is not None, "it should have found the riser"
    assert 4.5 < near["rangeM"] < 5.5, near


def test_a_sonar_is_not_perfect():
    """A controller that trusts every ping is one that will be surprised.

    Some beams do not come back and the ranges that do are not exact, so a
    plan made on a single ping is a plan made on one sample of an instrument
    that has noise in it.
    """
    world = World({"things": [{"id": "block", "kind": "mooring-block",
                               "x": 6.0, "y": 0.0, "z": -0.3}]})
    one = Sonar({"rangeM": [0.5, 10.0], "horizontalFovDeg": 130,
                 "missesShare": 0.3, "rangeNoiseM": 0.08}, seed=11)
    returns, ranges = set(), set()
    for i in range(40):
        one.ping(float(i), np.zeros(3), FORWARD, world, None)
        returns.add(one.said()["returns"])
        near = one.nearest()
        assert near is not None, "a target this wide is never lost entirely"
        ranges.add(round(near["rangeM"], 3))
    # Beams drop out, so the number that come back is not the same every ping.
    assert len(returns) > 1, f"every ping returned the same {returns}"
    # And the range is a measurement, not a lookup.
    assert len(ranges) > 5, f"only {len(ranges)} different ranges in forty pings"


def test_it_pings_at_its_own_rate_and_not_every_step():
    """A sonar that pinged at two hundred hertz is a sonar that does not exist."""
    one = a_sonar(pingsPerSecond=5.0)
    assert one.due(0.0)
    one.ping(0.0, np.zeros(3), FORWARD, World(None), None)
    assert not one.due(0.1)
    assert one.due(0.25)


def test_a_controller_avoids_what_it_was_not_told_about():
    """The point of having a sonar at all, flown.

    Two dives, the same in every respect but who is at the controls: a route
    straight through a nursery frame nobody mentioned. The planner flies the
    route it was given, because a route is a list of points and a point is not
    a warning. The same controller with the sonar switched on declines.
    """
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import Dive

    vehicle = _pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"
    model = Hydrodynamics.from_package(vehicle / "dynamics.json")

    def fly(who: str):
        objective = {"kind": "reach", "dx": 40.0, "dy": 0.0, "radiusM": 2.0,
                     "timeLimitS": 280.0, "controller": who}
        brief = {"durationSeconds": 300, "seed": 5, "vehiclePath": str(vehicle),
                 "initialState": {"positionM": [0.0, 0.0, -6.0], "tetherOutM": 0.0},
                 "conditions": {"kind": "constructed", "parameters": {}},
                 "objective": objective,
                 # A frame twenty metres ahead, right on the way.
                 "layout": {"things": [{"id": "frame", "kind": "nursery-frame",
                                        "x": 20.0, "y": 0.0, "z": -7.0}]}}
        dive = Dive(brief, Body(model), Allocator(model),
                    _pathlib.Path("nowhere.usda"), lambda kind, **said: None)
        dive.floor = -12.0
        dive.begin_task(objective)
        closest = 1e9
        for _ in range(int(280 / dive.dt)):
            dive.step()
            closest = min(closest, float(np.linalg.norm(
                dive.position[:2] - np.array([20.0, 0.0]))))
            if dive.done:
                break
        return dive, closest

    blind, blind_closest = fly("pursue")
    wary, wary_closest = fly("wary")

    assert blind.sonar is not None and blind.sonar.pings > 0, "the sonar should have run"
    # The blind one drives at it and is stopped by it.
    assert blind.world.struck > 0, "the planner should have run into the frame"
    # The wary one keeps its distance and never touches it.
    assert wary.world.struck == 0, (
        f"it hit the frame anyway, getting within {wary_closest:.1f} m")
    assert wary_closest > blind_closest, (
        f"wary came within {wary_closest:.1f} m and blind within {blind_closest:.1f} m")
    assert wary.helm.controllers["wary"].avoided > 0, "and it should say it saw something"


def test_a_tank_wall_returns_an_echo():
    """Inside a 2 x 1 m tank, a beam straight ahead from the middle hits the
    end glass a metre away, and one to the side hits the side glass."""
    import numpy as np
    from sonar import Sonar

    sonar = Sonar({"beams": 3, "horizontalFovDeg": 90, "beamWidthDeg": 25,
                   "rangeM": [0.3, 100.0], "rangeNoiseM": 0.0, "missesShare": 0.0})
    walls = (np.array([-1.0, -0.5, -0.95]), np.array([1.0, 0.5, 0.0]))
    got = sonar.ping(0.0, np.array([0.0, 0.0, -0.4]), np.eye(3), walls=walls)
    assert abs(got[1] - 1.0) < 1e-6
    assert abs(got[0] - 0.5 / np.sin(np.radians(45))) < 1e-6
    assert abs(sonar.spread() - np.radians(25)) < 1e-9


def test_wary_sees_what_is_ahead_when_the_sides_are_closer():
    """In a tank the side beams hear the glass first; a pillar dead ahead
    must still count, and the way round is the side with more water."""
    import math
    import numpy as np
    from controllers.base import Observation
    from controllers.wary import WaryController

    wary = WaryController(np.full(6, 10.0), np.full(6, 3.0), 0.0, 0.005)
    wary.tune("standOffM", 0.3)
    wary.tune("aheadDeg", 40.0)
    seen = Observation.__new__(Observation)
    seen.seen = {"rangeM": 0.2, "bearingRad": math.radians(-45), "beam": 0}
    seen.sonar = {"bearingsRad": np.radians([-45.0, 0.0, 45.0]), "rangesM": np.array([0.4, 0.25, 0.9])}
    close = wary.in_the_way(seen)
    assert close is not None and abs(close["rangeM"] - 0.25) < 1e-9
    assert wary.the_gap(seen, close) > 0


def test_wary_remembers_each_ping_once_and_detours_to_the_open_side():
    """A ping handed over on every control step is one ping; and a pillar
    remembered across the leg sends the vehicle round its open side."""
    import math
    import numpy as np
    from controllers.base import Observation
    from controllers.wary import WaryController

    wary = WaryController(np.full(6, 10.0), np.full(6, 3.0), 0.0, 0.005)
    for name, value in (("standOffM", 0.3), ("clearanceM", 0.24), ("rememberS", 10.0)):
        wary.tune(name, value)
    wary.route = [{"x": -0.55, "y": -0.15}]
    wary.at = 0
    seen = Observation.__new__(Observation)
    seen.t = 1.0
    seen.position = np.array([0.2, -0.15, -0.4])
    seen.rotation = np.array([[-1.0, 0, 0], [0, -1.0, 0], [0, 0, 1.0]])
    seen.velocity = np.zeros(6)
    seen.sonar = {"bearingsRad": np.radians([-25.0, 0.0, 25.0]), "rangesM": np.array([np.nan, 0.5, np.nan])}
    for _ in range(200):
        wary.remember(seen)
    assert len(wary.heard) == 1
    here = seen.position[:2]
    assert wary.in_corridor(here, np.array([-0.55, -0.15]), 0.24)
