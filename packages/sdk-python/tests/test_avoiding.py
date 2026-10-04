"""The example that reads the sonar, and the one piece of it with real reasoning.

The SDK had no example that read the sonar at all, which left the one instrument a
controller learns from — everything else it is handed comes from the dive —
without a starting point. `examples/avoid.py` is that starting point, and what has
to be right is where it thinks the gap is.
"""

import importlib.util
import math
import pathlib
import sys

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
# The SDK itself, so the example can import it the way a customer's would.
sys.path.insert(0, str(HERE.parent))

EXAMPLE = HERE.parent / "examples/avoid.py"


def a_controller():
    spec = importlib.util.spec_from_file_location("avoid_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GoAroundThings()


def a_fan(ranges, across=math.radians(60)):
    """A fan of returns, evenly spread either side of the nose."""
    bearings = np.linspace(-across, across, len(ranges))
    return {"bearingsRad": list(bearings), "rangesM": list(ranges)}


def test_an_empty_fan_is_no_reason_to_turn():
    """The ordinary case, and the one worth being cheap about: nothing came back
    from any beam, so the heading the dive gave stands."""
    one = a_controller()
    nothing = [float("nan")] * 32
    assert one.the_widest_gap(a_fan(nothing)) is None
    # And a fan of distant returns is equally no reason.
    assert one.the_widest_gap(a_fan([40.0] * 32)) is None


def test_it_steers_at_the_middle_of_the_gap_and_not_away_from_the_return():
    """The trap the interface names: a thing dead ahead is symmetric, so the
    closest beam flips between the two either side of centre as the noise moves.
    A controller told to turn away from *that* goes left, then right, then left,
    and drives into the thing while chattering.
    """
    one = a_controller()
    # Something dead ahead: the middle third of the fan is blocked.
    ranges = [float("nan")] * 32
    for i in range(12, 20):
        ranges[i] = 4.0
    gap = one.the_widest_gap(a_fan(ranges))
    assert gap is not None
    # It picks one side, decisively, rather than splitting the difference at zero.
    assert abs(gap) > math.radians(10)


def test_the_gap_is_the_widest_one_and_not_the_first():
    """A narrow slot nearer the nose is not better than an open flank."""
    one = a_controller()
    ranges = [5.0] * 32
    ranges[15] = float("nan")              # a one-beam slot dead ahead
    for i in range(24, 32):                # and a wide opening to starboard
        ranges[i] = float("nan")
    gap = one.the_widest_gap(a_fan(ranges))
    assert gap is not None
    assert gap > math.radians(20), "it went for the slot instead of the flank"


def test_a_fan_with_nowhere_open_still_answers():
    """Turning hard one way is worse than splitting the difference and driving
    straight in, so it does not return None and let the route take over."""
    one = a_controller()
    assert one.the_widest_gap(a_fan([3.0] * 32)) is not None


def test_a_malformed_fan_is_not_a_reason_to_turn():
    """A fan whose bearings and ranges disagree is an instrument fault, and
    inventing a turn out of it would be worse than flying the route."""
    one = a_controller()
    assert one.the_widest_gap({"bearingsRad": [0.0, 0.1], "rangesM": [3.0]}) is None
    assert one.the_widest_gap({}) is None


def test_it_declares_that_it_needs_a_sonar():
    """A dive that fitted no sonar would fly this as a route follower and the
    row would say it never avoided anything, with no reason given."""
    one = a_controller()
    assert "imaging_sonar" in one.needs


def test_a_deployed_controller_can_actually_see_the_sonar():
    """The gap this example exists to close, held so it cannot reopen.

    The runtime has published `/sonar/scan` all along — "the message a collision
    avoider expects", in its own words — the catalogue declares the topic, and the
    interface documents the field. Nothing in the SDK listened, so
    `Observation.sonar` was always None for a deployed controller and an
    obstacle-avoiding one could not be written against this interface at all.
    """
    import math

    from iocean.sensing import Navigator

    n = Navigator()
    # As `LaserScan` sends it: infinity for a beam that came back with nothing.
    n.sonar_fan([-0.4, -0.2, 0.0, 0.2, 0.4],
                [math.inf, 6.0, 3.5, math.inf, math.inf])
    seen = n.observation(0.0)
    assert seen.sonar is not None
    assert len(seen.sonar["rangesM"]) == 5
    # Infinity becomes NaN, because the interface says nothing-there with NaN.
    assert math.isnan(seen.sonar["rangesM"][0])
    assert seen.sonar["rangesM"][2] == 3.5
    # And the nearest return is the convenience the interface promises.
    assert seen.seen == {"rangeM": 3.5, "bearingRad": 0.0, "beam": 2}


def test_a_vehicle_with_no_sonar_says_so_rather_than_seeing_an_empty_sea():
    """None, not an empty fan: a controller told the water is clear would fly
    into things, and a controller told nothing is known can refuse."""
    from iocean.sensing import Navigator

    n = Navigator()
    seen = n.observation(0.0)
    assert seen.sonar is None
    assert seen.seen is None


def test_the_example_flies_the_altitude_the_task_asks_for():
    """A controller that ignored the task would score badly for a reason that has
    nothing to do with what it is for — and would fly a different path from the
    baseline it is compared against, which makes the comparison meaningless rather
    than merely unfair. That is what `avoid`'s first platform row was: `struck 0`
    against two baselines' 3 of 3, and a closest approach of nineteen metres."""
    one = a_controller()
    assert one["altitudeM"] == 3.0                     # its own default
    one.tasked({"kind": "transect", "altitudeM": 5.0, "speedMs": 0.6})
    assert one["altitudeM"] == 5.0
    assert one["speedMs"] == 0.6
    # And the goal is kept, the way the base class promises.
    assert one.goal["kind"] == "transect"


def test_a_task_that_says_nothing_about_altitude_leaves_the_default():
    """A goal is not a full configuration; a field it omits is not a zero."""
    one = a_controller()
    one.tasked({"kind": "reach", "dx": 40, "dy": 0})
    assert one["altitudeM"] == 3.0
    one.tasked({"altitudeM": "not a number"})
    assert one["altitudeM"] == 3.0, "a field that will not read is left alone"


def test_the_side_is_remembered_and_the_bearing_is_not():
    """The bug the first version of this file had, and it is a subtle one.

    A gap is a bearing **off the nose**. Store one on one tick and apply it on the
    next — after the vehicle has turned towards it — and it asks for the same turn
    again, and again: a vehicle going in circles rather than round something. So
    only which way round is remembered, and the bearing is remeasured from every
    sweep.
    """
    one = a_controller()
    ranges = [float("nan")] * 32
    for i in range(12, 20):
        ranges[i] = 4.0
    first = one.the_widest_gap(a_fan(ranges))
    assert first is not None
    side = 1.0 if first >= 0 else -1.0
    # Asked again with the same sweep and the side committed, it gives the same
    # bearing — it is a measurement, not an accumulator.
    assert one.the_widest_gap(a_fan(ranges), side) == pytest.approx(first)
    # And the example keeps the side, not the bearing.
    source = EXAMPLE.read_text()
    assert "self.committed = 1.0 if gap >= 0 else -1.0" in source
    assert "wanted = wrap(seen.heading + gap)" in source


def test_it_keeps_going_round_the_way_it_started():
    """A vehicle that changes its mind halfway round a frame passes neither side
    of it. So an opening on the committed side is taken even when a wider one has
    opened on the other."""
    one = a_controller()
    ranges = [5.0] * 32
    for i in range(2, 8):                  # a modest opening to port
        ranges[i] = float("nan")
    for i in range(20, 32):                # a wider one to starboard
        ranges[i] = float("nan")
    # Uncommitted, it takes the wider opening.
    assert one.the_widest_gap(a_fan(ranges)) > 0
    # Committed to port, it stays to port.
    assert one.the_widest_gap(a_fan(ranges), -1.0) < 0


def test_a_fan_with_nowhere_open_turns_the_way_it_was_already_going():
    """Rather than splitting the difference, which is straight ahead."""
    one = a_controller()
    blocked = [3.0] * 32
    assert one.the_widest_gap(a_fan(blocked), 1.0) > 0
    assert one.the_widest_gap(a_fan(blocked), -1.0) < 0


def test_it_goes_round_a_frame_in_the_tank():
    """The whole chain, end to end, on one controller.

    Measured both ways over the same three frames on the same path: with no sonar
    fitted it struck them 1073 times and came within 1.5 m of each; with the sonar
    fitted it struck nothing and kept better than six metres clear. The difference
    is not the controller — it is the same class — it is whether anything gave it
    the fan.
    """
    import math

    sys.path.insert(0, str(HERE.parents[2] / "services/sim-runtime/coral"))
    from iocean.tank import Tank

    one = a_controller()
    frame = {"id": "one", "kind": "nursery-frame", "x": 14.0, "y": 0.6,
             "groundM": 12.0, "heightM": 6.0, "radiusM": 2.0}
    task = {"kind": "reach", "dx": 30, "dy": 0, "radiusM": 3.0, "timeLimitS": 70}
    tank = Tank("bluerov2", task=task, seconds=70.0, things=[frame])
    seen = tank.reset()
    assert tank.dive.sonar is not None, "the tank fitted no sonar"
    assert len(tank.dive.world) == 1, "the frame is not in the water"
    one.engage(seen)
    closest = None
    while not tank.done:
        seen, _, _, _ = tank.step(one.observe(seen))
        gap = math.hypot(seen.position[0] - frame["x"], seen.position[1] - frame["y"])
        closest = gap if closest is None else min(closest, gap)
    assert one.status()["avoiding"] > 0, "it never saw the frame"
    assert tank.dive.world.struck == 0, f"it hit the frame; closest {closest:.2f} m"
    # Clear of the frame itself, not merely not touching it.
    assert closest > frame["radiusM"], f"closest approach {closest:.2f} m"


def test_a_controller_is_told_how_far_it_is_to_the_bottom():
    """Reef work is altitude work, and a transect is *scored* on holding one.

    A Doppler log measures the seabed to get velocity over the ground, so it knows
    the range to it and every real one reports it. The bridge published the twist
    and not the range, so `Observation.floor` was always None for anything deployed
    and a customer's controller could not fly the task it was being scored on.
    """
    from iocean.sensing import GRAVITY, SURFACE_PRESSURE_PA, Navigator

    n = Navigator(density=1025.0)
    n.pressure(SURFACE_PRESSURE_PA + 1025.0 * GRAVITY * 8.0)      # eight metres down
    n.imu((1, 0, 0, 0), (0, 0, 0))
    n.bottom(3.0, 0.05, 50.0)                                      # three metres up
    seen = n.observation(0.0)
    assert seen.floor == pytest.approx(-11.0, abs=0.01), "eight down, three up, floor at -11"
    # And the altitude a controller works with is the difference.
    assert seen.position[2] - seen.floor == pytest.approx(3.0, abs=0.01)


def test_losing_bottom_lock_says_unknown_rather_than_stale():
    """A controller told a stale floor holds an altitude over where the bottom used
    to be, and flies into the next head. Outside the log's bounds is no reading."""
    from iocean.sensing import GRAVITY, SURFACE_PRESSURE_PA, Navigator

    n = Navigator(density=1025.0)
    n.pressure(SURFACE_PRESSURE_PA + 1025.0 * GRAVITY * 8.0)
    n.imu((1, 0, 0, 0), (0, 0, 0))
    n.bottom(3.0, 0.05, 50.0)
    assert n.observation(0.0).floor is not None
    # Over deep water: the bottom is past the log's reach.
    n.bottom(float("inf"), 0.05, 50.0)
    assert n.observation(1.0).floor is None
    # And too close to read is equally no reading.
    n.bottom(0.01, 0.05, 50.0)
    assert n.observation(2.0).floor is None


def test_the_tank_reports_the_bottom_too():
    """So an altitude-holding controller can be tried before it is deployed."""
    sys.path.insert(0, str(HERE.parents[2] / "services/sim-runtime/coral"))
    from iocean.tank import Tank

    task = {"kind": "reach", "dx": 10, "dy": 0, "radiusM": 3.0, "timeLimitS": 20}
    tank = Tank("bluerov2", task=task, seconds=20.0)
    seen = tank.reset()
    for _ in range(20):
        seen, _, _, _ = tank.step(None)
    truth = tank.dive.observation()
    if truth.floor is None:
        # A tank with no seabed has no bottom to report, and says so.
        assert seen.floor is None
    else:
        assert seen.floor is not None, "the tank knows the floor and did not pass it on"
        assert seen.floor == pytest.approx(truth.floor, abs=0.5)


def test_every_vehicle_with_a_doppler_log_declares_the_range():
    """The contract a customer reads to know what the vehicle sends."""
    from iocean import vehicles

    for slug in ("bluerov2", "bluerov2-heavy", "remus-100"):
        described = vehicles.load(slug)
        assert "dvl" in described.carries, slug
        topics = {one.name for one in described.publishes}
        assert "/dvl/range" in topics, f"{slug} publishes a twist and not a range"
