"""The tank runs the runtime's physics; a controller that holds here holds there."""

import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples"))

from iocean import Command, Controller  # noqa: E402
from iocean.tank import Tank  # noqa: E402
from iocean.tasks import hold_station, waypoints  # noqa: E402
from hold import StationHold  # noqa: E402


def test_the_example_holds_station_through_its_sensors():
    tank = Tank("bluerov2", start=(0.0, 0.0, -7.0), seconds=45.0, task=hold_station(seconds=40), sensed=True)
    report = tank.run(StationHold())
    assert report.score > 0.8, str(report)
    assert report.task["kind"] == "hold-station" and report.task["done"]
    assert abs(report.final["depthM"] - 7.0) < 0.1


def test_a_target_depth_is_reached():
    controller = StationHold()
    controller.tune("depthM", 9.0)
    tank = Tank("bluerov2", seconds=60.0)
    report = tank.run(controller)
    assert abs(report.final["depthM"] - 9.0) < 0.15, str(report)


def test_waypoints_are_scored_by_the_runtime():
    # A hold never moves, so it reaches none of them; the score says so.
    tank = Tank("bluerov2", seconds=10.0, task=waypoints(points=[{"dx": 5, "dy": 0}], time_limit_s=10))
    report = tank.run(StationHold())
    assert report.score == 0.0 and report.task["achieved"]["of"] == 1


def test_stepping_it_yourself_like_a_learner():
    tank = Tank("bluerov2", seconds=5.0, task=hold_station(seconds=5), sensed=False)
    seen = tank.reset()
    steps = 0
    while not tank.done:
        seen, reward, done, info = tank.step(Command.nothing())
        steps += 1
        assert info["flying"] == "stack"
    assert steps == 5 * 20
    # Doing nothing, the catalogue vehicle sinks and the score says so.
    assert seen.depth > 7.1
    assert tank.report().score < 1.0


def test_the_wrong_vehicle_is_refused_before_a_step():
    class ForTheHeavy(Controller):
        vehicle = "bluerov2-heavy"

        def observe(self, seen):
            return Command.nothing()

    with pytest.raises(ValueError, match="cannot fly"):
        Tank("bluerov2").run(ForTheHeavy())


def test_thruster_commands_reach_the_thrusters():
    class Spin(Controller):
        vehicle = "bluerov2"
        commands = "thrusters"

        def observe(self, seen):
            # Yaw with the four horizontals, as the vehicle lists them.
            return Command.thrusters_of(0.3, -0.3, -0.3, 0.3, 0.0, 0.0)

    tank = Tank("bluerov2", seconds=6.0, sensed=False)
    report = tank.run(Spin())
    assert abs(report.final["headingDeg"]) > 5.0


def test_a_current_is_felt_and_the_hold_fights_it():
    still = Tank("bluerov2", seconds=30.0, task=hold_station(seconds=30), sensed=False).run(StationHold())
    moving = Tank("bluerov2", seconds=30.0, task=hold_station(seconds=30), sensed=False,
                  current=(0.3, 90.0)).run(StationHold())
    assert moving.task["thrusterEffort"] > still.task["thrusterEffort"] * 2, "holding in a current costs thrust"
    # It is felt, and it is not held: the example scores about 0.28 in a third of
    # a knot. That assertion used to read `> 0.8` and passed, because the tank
    # fitted the vehicle **no instruments and no tether** — it built the dive with
    # no `vehiclePath`, so `switch_on_the_tether` and its siblings found no package
    # to read. A platform dive always has one. So the tank was materially easier
    # than the thing it exists to stand in for, and "a controller that holds here
    # holds there" was false in the direction that flatters: a hold tuned here and
    # deployed drifts.
    #
    # And it *is* held now, at 0.3 m/s: the hold carries its error, which is what
    # lets it settle on station rather than wherever its own push balances the drag.
    # Before that it scored 0.094 at one knot and sat 1.60 m off; it now scores
    # 0.560 and sits 0.17 m off, measured against the truth and not its estimate.
    assert moving.score > 0.9, str(moving)
    # What its own navigation believed, which is a different and larger number: no
    # seabed in a tank means no bottom lock, so the reckoning walks off at about the
    # current's speed. A report that showed only that read as a broken hold.
    assert moving.final["believedOffStartM"] > moving.final["offStartM"] + 1.0


def test_the_tank_fits_what_the_vehicle_carries():
    """Which is the whole of the promise: the same class, the same vehicle.

    Without a `vehiclePath` in the brief the dive fits nothing the package declares
    — no sonar, no CTD, no modem, no **tether** — and a BlueROV2 without its tether
    is a easier vehicle to fly than the one anybody has. A controller that avoids
    things could not be tried at all, and one that holds station was tuned against
    a vehicle that does not exist.
    """
    tank = Tank("bluerov2", seconds=5.0, task=hold_station(seconds=5), sensed=False)
    assert "vehiclePath" in tank.brief
    assert tank.dive.sonar is not None, "the BlueROV2 declares an imaging sonar"
    assert tank.dive.tether is not None, "and it is on the end of a tether"


def test_a_tank_can_have_things_in_the_water():
    """Or a controller whose job is not hitting things has nothing to not hit."""
    frames = [{"id": "one", "kind": "nursery-frame", "x": 6.0, "y": 0.0,
               "groundM": 12.0, "heightM": 6.0, "radiusM": 2.0}]
    tank = Tank("bluerov2", seconds=5.0, task=hold_station(seconds=5), things=frames)
    assert len(tank.dive.world) == 1
    # And none by default, because a tank with furniture nobody asked for is worse
    # than an empty one.
    assert len(Tank("bluerov2", seconds=5.0, task=hold_station(seconds=5)).dive.world) == 0
