"""Knowing where you are by the model you fly, and selling the error.

A Seaglider carries no Doppler log — too hungry for ten months — and hears no
acoustic fix underwater. It estimates its speed through the water from the
hydrodynamic model it flies by, integrates that for hours, and finds out how
wrong it was when GPS comes back.

Then the gap between where it reckoned it would surface and where it actually
did, over the time it was down, is the depth-averaged current. Every other row
in the positioning table treats that gap as the error being studied. This one
hands it over as the result.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from navigation import Navigation


def level():
    return np.eye(3)


def fly(nav, seconds, body_velocity, current, dt=1.0, depth=100.0, floor=None):
    """Carry a vehicle through the water with a current on it.

    `body_velocity` is what it is doing over the ground, which is what the
    simulator knows; the current is what the water is doing, which the vehicle
    does not.
    """
    nav.current = np.asarray(current, dtype=float)
    position = np.array([0.0, 0.0, -depth])
    for i in range(int(seconds / dt)):
        position[:2] += np.asarray(body_velocity, dtype=float)[:2] * dt
        nav.step(float(i) * dt, position, np.asarray(body_velocity, dtype=float),
                 level(), floor, dt)
    return position


def test_a_log_on_the_bottom_sees_the_ground_and_the_current_is_free():
    """A Doppler log pings the seabed, so the current is already in what it
    reads and costs nothing."""
    locked = Navigation(suite={"dvl": True}, aiding={"kind": "none"},
                        began_at=[0.0, 0.0, -10.0], seed=1)
    truth = fly(locked, 600.0, body_velocity=[0.5, 0.0, 0.0], current=[0.3, 0.0, 0.0],
                depth=10.0, floor=-30.0)
    assert locked.bottom_lock

    # The same flight with nothing to ping. Both carry a compass bias and a
    # scale error; only one of them is also being carried by water it cannot
    # see, and over ten minutes that is the difference.
    blind = Navigation(suite={"dvl": False, "flightModel": True, "flightModelError": 0.0},
                       aiding={"kind": "none"}, began_at=[0.0, 0.0, -100.0], seed=1)
    blind_truth = fly(blind, 600.0, body_velocity=[0.5, 0.0, 0.0], current=[0.3, 0.0, 0.0])
    assert not blind.bottom_lock
    assert blind.drift(blind_truth) > 5.0 * locked.drift(truth), (
        f"log {locked.drift(truth):.0f} m against no log {blind.drift(blind_truth):.0f} m")


def test_without_a_log_the_current_is_invisible_and_becomes_the_error():
    """The error no amount of better instrumentation fixes."""
    nav = Navigation(suite={"dvl": False, "flightModel": True, "flightModelError": 0.0},
                     aiding={"kind": "none"}, began_at=[0.0, 0.0, -100.0], seed=1)
    truth = fly(nav, 600.0, body_velocity=[0.5, 0.0, 0.0], current=[0.2, 0.0, 0.0])
    # It flew 0.5 m/s over the ground, of which 0.2 was the water carrying it.
    # It believes it did 0.3. Over ten minutes that is 120 m of error.
    assert not nav.bottom_lock
    assert 100.0 < nav.drift(truth) < 140.0, f"drifted {nav.drift(truth):.0f} m"


def test_a_flight_model_is_a_better_guess_than_no_guess():
    """A glider's model is fitted to its own dives; a vehicle inferring speed
    from thrust and drag is wrong by a fifth all day."""
    flown = Navigation(suite={"dvl": False, "flightModel": True, "flightModelError": 0.03},
                       aiding={"kind": "none"}, began_at=[0.0, 0.0, -100.0], seed=7)
    guessed = Navigation(suite={"dvl": False}, aiding={"kind": "none"},
                         began_at=[0.0, 0.0, -100.0], seed=7)
    assert abs(flown.flight_scale - 1.0) < abs(guessed.blind_scale - 1.0)


def test_surfacing_turns_the_drift_into_the_current():
    """The product of a glider dive."""
    nav = Navigation(suite={"dvl": False, "flightModel": True, "flightModelError": 0.0},
                     aiding={"kind": "none"}, began_at=[0.0, 0.0, -0.2], seed=3)
    # Down for an hour, carried east at a fifth of a metre a second.
    carried = [0.25, 0.0, 0.0]
    water = [0.2, 0.0, 0.0]
    truth = fly(nav, 3600.0, body_velocity=carried, current=water, dt=1.0, depth=100.0)

    # Back to the surface, where there is sky.
    truth[2] = -0.1
    nav.step(3601.0, truth, np.array([0.0, 0.0, 0.0]), level(), None, 1.0)

    assert nav.depth_averaged_current is not None, "it should have worked out the water"
    got = float(np.hypot(*nav.depth_averaged_current[:2]))
    assert abs(got - 0.2) < 0.05, f"said {got:.3f} m/s, the water was doing 0.200"
    assert nav.said(truth, 3601.0)["depthAveragedCurrentSpeedMs"] == round(got, 4)


def test_a_vehicle_that_was_being_fixed_all_along_says_nothing_about_the_water():
    """An array corrects the vehicle towards the truth, so the gap at the end
    is not the water — it is what the last fix left behind."""
    nav = Navigation(suite={"dvl": False}, aiding={"kind": "lbl", "everyS": 10.0,
                                                   "accuracyM": 0.5, "rangeM": 5000.0},
                     began_at=[0.0, 0.0, -0.2], seed=3)
    truth = fly(nav, 1200.0, body_velocity=[0.25, 0.0, 0.0], current=[0.2, 0.0, 0.0], depth=100.0)
    truth[2] = -0.1
    nav.step(1201.0, truth, np.array([0.0, 0.0, 0.0]), level(), None, 1.0)
    assert nav.depth_averaged_current is None


# ── an array is its transponders ─────────────────────────────────────────────

def test_an_array_somebody_laid_is_heard_from_where_it_reaches():
    """An array is not a circle round a point.

    It is four or five things on the seabed, and whether a fix can be had is
    decided by how many of them the vehicle can hear — three, to cut a
    position. That is a different shape from a circle: at the edge of a real
    array you lose the far side first, and the fixes stop before you have left
    the middle of anything.
    """
    nav = Navigation(suite={"dvl": True},
                     aiding={"kind": "lbl", "everyS": 1.0, "accuracyM": 0.5, "rangeM": 60.0},
                     began_at=[0.0, 0.0, -14.0], seed=5)
    # Four laid on a square of fifty metres.
    nav.transponders = [np.array([0.0, 0.0, -14.0]), np.array([50.0, 0.0, -14.0]),
                        np.array([50.0, -50.0, -14.0]), np.array([0.0, -50.0, -14.0])]

    middle = np.array([25.0, -25.0, -12.0])
    nav.last_fix_t = None
    nav.maybe_fix(10.0, middle)
    assert nav.fixes == 1, "in the middle it hears all four"
    assert "transponders" in nav.last_fix_from

    # Two hundred metres away it hears none of them, and a fix it cannot take
    # is not a worse fix — it is no fix.
    was = nav.fixes
    nav.last_fix_t = None
    nav.maybe_fix(20.0, np.array([260.0, -25.0, -12.0]))
    assert nav.fixes == was, "out of range of every one of them"


def test_hearing_two_of_them_is_not_a_position():
    nav = Navigation(suite={"dvl": True},
                     aiding={"kind": "lbl", "everyS": 1.0, "accuracyM": 0.5, "rangeM": 30.0},
                     began_at=[0.0, 0.0, -14.0], seed=5)
    nav.transponders = [np.array([0.0, 0.0, -14.0]), np.array([20.0, 0.0, -14.0]),
                        np.array([200.0, 0.0, -14.0]), np.array([220.0, 0.0, -14.0])]
    nav.last_fix_t = None
    nav.maybe_fix(10.0, np.array([10.0, 0.0, -12.0]))
    assert nav.fixes == 0, "two in range is a pair of ranges, not a fix"
