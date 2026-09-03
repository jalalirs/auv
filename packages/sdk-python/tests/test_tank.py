"""The tank runs the runtime's physics; a controller that holds here holds there."""

import math
import pathlib
import sys

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples"))

from coral_city import Command, Controller  # noqa: E402
from coral_city.tank import Tank  # noqa: E402
from coral_city.tasks import hold_station, waypoints  # noqa: E402
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
    assert moving.score > 0.8, str(moving)
    assert moving.task["thrusterEffort"] > still.task["thrusterEffort"] * 2, "holding in a current costs thrust"
