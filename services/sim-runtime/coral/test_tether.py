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

from tether import Tether


def hanging(length: float, out: float = 40.0, current=(0.0, 0.0, 0.0)) -> Tether:
    """A cable from a ship on the surface to a vehicle `out` metres down."""
    one = Tether({"lengthM": length})
    surface = np.array([0.0, 0.0, 0.0])
    vehicle = np.array([0.0, 0.0, -out])
    one.start(surface, vehicle)
    one.settle(vehicle, np.asarray(current), passes=3000)
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


def test_a_working_scope_in_a_current_is_the_larger_force():
    """The case it was wrong about, which is every working day.

    A BlueROV2 at a quarter of a knot costs about two newtons to push through
    the water. The cable it is on costs several times that — an 8 mm tether has
    more than ten times the frontal area of the vehicle hanging off it — and a
    pilot who has flown one knows it.
    """
    speed = 0.26
    current = np.array([speed, 0.0, 0.0])
    working = hanging(55.0, out=50.0, current=current)
    cable = float(np.linalg.norm(working.pull(current)))
    hull = hull_drag(speed)
    assert cable > 2.0 * hull, (
        f"the cable pulled {cable:.1f} N and the hull costs {hull:.1f} N to push: "
        "leaving the tether out was defensible after all")


def test_a_short_tether_is_a_much_smaller_thing():
    """Which is why "how much is out" is a question worth asking."""
    current = np.array([0.26, 0.0, 0.0])
    ten = float(np.linalg.norm(hanging(12.0, out=10.0, current=current).pull(current)))
    fifty = float(np.linalg.norm(hanging(55.0, out=50.0, current=current).pull(current)))
    assert fifty > 4.0 * ten, (
        f"fifty metres pulled {fifty:.1f} N and ten pulled {ten:.1f} N")


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


def test_the_pull_does_not_depend_on_how_long_you_relaxed_it():
    """The bug that made the first version of this useless.

    Taking the whole cable's equilibrium — two end tensions, three equations —
    is ill-posed exactly where it matters. A cable that streams out and comes
    back has both ends pulling along nearly the same line, the two unknowns
    stop being independent, and the split between them swings on rounding: the
    same cable answered 6 N, then 10, then 13 as it was relaxed further, while
    the shape itself had stopped moving. Solved node by node it is the same
    answer twice.
    """
    current = np.array([0.26, 0.0, 0.0])
    for out, length in ((6.3, 100.0), (50.0, 55.0), (50.0, 110.0)):
        settled = []
        for passes in (2000, 8000):
            one = Tether({"lengthM": length})
            vehicle = np.array([0.0, 0.0, -out])
            one.start(np.zeros(3), vehicle, current)
            one.settle(vehicle, current, passes=passes)
            settled.append(float(np.linalg.norm(one.pull(current))))
        assert abs(settled[0] - settled[1]) < 0.1 * max(0.5, settled[1]), (
            f"{length} m to {out} m down gave {settled[0]:.2f} N then {settled[1]:.2f} N")


def test_a_slack_bight_near_the_surface_pulls_much_less_than_a_taut_scope():
    """Which is why "how much is out" is not the same question as "how long".

    A hundred metres paid out to a vehicle six metres down is ninety metres of
    cable streaming downstream in a bight, and a bight pulls on the end that is
    holding it up rather than on the one on the bottom. Fifty-five metres to a
    vehicle fifty metres down is the same cable doing the job it is for.
    """
    current = np.array([0.26, 0.0, 0.0])
    bight = hanging(100.0, out=6.3, current=current)
    scope = hanging(55.0, out=50.0, current=current)
    loose = float(np.linalg.norm(bight.pull(current)))
    working = float(np.linalg.norm(scope.pull(current)))
    assert working > 4 * loose, (
        f"the working scope pulled {working:.2f} N and the bight {loose:.2f} N")


def test_a_vehicle_cannot_reach_past_its_cable():
    """Flown, rather than asserted about a sphere.

    The BlueROV2's package says it comes on a hundred metres of tether, and a
    hundred metres of tether is a hard limit on where it can get to. This is
    how the tether announced itself: a navigation test that had asked the
    vehicle to reach a point a hundred and twenty metres away, and had done so
    happily for months, stopped at a hundred and nought-point-three.
    """
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import Dive

    vehicle = _pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"
    model = Hydrodynamics.from_package(vehicle / "dynamics.json")
    brief = {"durationSeconds": 900, "seed": 4, "vehiclePath": str(vehicle),
             "initialState": {"positionM": [0, 0, -6], "tetherOutM": 40.0},
             "conditions": {"kind": "constructed", "parameters": {}}}
    dive = Dive(brief, Body(model), Allocator(model),
                _pathlib.Path("nowhere.usda"), lambda kind, **said: None)
    dive.floor = -12.0
    dive.begin_task({"kind": "reach", "dx": 120.0, "dy": 0.0, "radiusM": 2.0,
                     "timeLimitS": 900.0})
    assert dive.tether is not None and dive.tether.out, "it should be on a cable"
    for _ in range(int(600 / dive.dt)):
        dive.step()
        if dive.done:
            break
    far = float(np.linalg.norm(dive.position[:2] - np.array([0.0, 0.0])))
    assert far <= 40.5, f"it got {far:.1f} m out on forty metres of cable"
    assert far > 35.0, f"it only got {far:.1f} m out, so something else stopped it"
    assert dive.tether.struck > 0, "and it should have said it reached the end"
