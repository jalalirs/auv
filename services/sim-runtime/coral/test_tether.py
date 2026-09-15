"""What a hundred metres of cable does.

The only thing in this plan that was wrong rather than missing: every tethered
dive in the record flew as though the umbilical were not there, and an 8 mm
tether has more than ten times the frontal area of the vehicle on the end of
it.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tether import Tether  # noqa: E402


def hanging(length: float, out: float = 40.0, current=(0.0, 0.0, 0.0)) -> Tether:
    """A cable from a ship on the surface to a vehicle `out` metres down."""
    one = Tether({"lengthM": length})
    surface = np.array([0.0, 0.0, 0.0])
    vehicle = np.array([0.0, 0.0, -out])
    one.start(surface, vehicle)
    one.settle(vehicle, np.asarray(current), passes=200)
    return one


def test_still_water_and_a_neutral_cable_pull_almost_nothing():
    """The case a simulator that ignored the tether was right about.

    A near-neutral cable hanging in still water is very nearly free, which is
    why leaving it out looked defensible for so long.
    """
    one = hanging(60.0)
    force = one.pull(np.zeros(3))
    assert float(np.linalg.norm(force)) < 2.0, f"{force} is not almost nothing"


# What the BlueROV2's own package says it costs to push it through water:
# the surge terms of its damping, which is the force this is measured against.
BLUEROV2_LINEAR, BLUEROV2_QUADRATIC = 4.03, 18.18


def hull_drag(speed: float) -> float:
    return BLUEROV2_LINEAR * speed + BLUEROV2_QUADRATIC * speed * speed


def test_a_hundred_metres_in_a_current_is_the_larger_force():
    """The case it was wrong about, which is every working day.

    A BlueROV2 at a quarter of a knot costs about two newtons to push through
    the water. A hundred metres of cable in the same water is a different order
    of thing — an 8 mm tether has more than ten times the frontal area of the
    vehicle on the end of it — and a pilot who has flown one knows it.
    """
    speed = 0.26
    current = np.array([speed, 0.0, 0.0])
    hundred = hanging(110.0, out=100.0, current=current)
    cable = float(np.linalg.norm(hundred.pull(current)))
    hull = hull_drag(speed)
    assert cable > 2.0 * hull, (
        f"the cable pulled {cable:.1f} N and the hull costs {hull:.1f} N to push: "
        "leaving the tether out was defensible after all")


def test_a_short_tether_is_a_much_smaller_thing():
    """Which is why "how much is out" is a question worth asking."""
    current = np.array([0.26, 0.0, 0.0])
    ten = float(np.linalg.norm(hanging(12.0, out=10.0, current=current).pull(current)))
    hundred = float(np.linalg.norm(hanging(110.0, out=100.0, current=current).pull(current)))
    assert hundred > 4.0 * ten, (
        f"a hundred metres pulled {hundred:.1f} N and ten pulled {ten:.1f} N")


def test_the_cable_leans_downstream():
    """A tether in a current is a catenary that leans, not one that hangs."""
    current = np.array([0.4, 0.0, 0.0])
    still = hanging(130.0, out=100.0)
    flowing = hanging(130.0, out=100.0, current=current)
    # The middle of the cable, downstream of where it hangs in still water.
    assert flowing.shape[10][0] > still.shape[10][0] + 5.0, (
        f"the middle moved from {still.shape[10][0]:.1f} to {flowing.shape[10][0]:.1f}")


def test_the_pull_is_towards_the_ship_when_the_vehicle_swims_away():
    """What a pilot feels: the cable is behind you, and it pulls back."""
    one = Tether({"lengthM": 60.0})
    surface = np.array([0.0, 0.0, 0.0])
    vehicle = np.array([50.0, 0.0, -20.0])
    one.start(surface, vehicle)
    one.settle(vehicle, np.zeros(3), passes=300)
    force = one.pull(np.zeros(3))
    if float(np.linalg.norm(force)) > 0.5:
        # Back the way it came, towards the surface end.
        towards = (surface - vehicle) / float(np.linalg.norm(surface - vehicle))
        assert float(np.dot(force, towards)) > 0, f"{force} does not pull back"


def test_a_vehicle_cannot_go_further_out_than_there_is_cable():
    one = Tether({"lengthM": 50.0})
    one.at = np.array([0.0, 0.0, 0.0])
    allowed, held = one.keep_in(np.array([80.0, 0.0, -10.0]), np.array([40.0, 0.0, -10.0]))
    assert held and one.taut
    assert abs(float(np.linalg.norm(allowed)) - 50.0) < 1e-6, allowed
    # And inside its reach it is not held at all.
    allowed, held = one.keep_in(np.array([10.0, 0.0, -10.0]), np.array([9.0, 0.0, -10.0]))
    assert not held and not one.taut


def test_a_cable_can_only_pull():
    """A slack cable in still water does not push the vehicle along."""
    one = Tether({"lengthM": 200.0})
    surface = np.array([0.0, 0.0, 0.0])
    vehicle = np.array([5.0, 0.0, -10.0])
    one.start(surface, vehicle)
    one.settle(vehicle, np.zeros(3), passes=300)
    force = one.pull(np.zeros(3))
    assert one.tension_n >= 0.0
    assert float(np.linalg.norm(force)) < 5.0, f"{force} from a slack cable"


def test_no_cable_is_no_force():
    one = Tether({"lengthM": 0.0})
    assert not one.out
    assert float(np.linalg.norm(one.pull(np.array([1.0, 0.0, 0.0])))) == 0.0
    where = np.array([500.0, 0.0, -10.0])
    allowed, held = one.keep_in(where, where)
    assert not held and np.array_equal(allowed, where)
