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
from coral_city.tasks import HoldStation, ReachDepth  # noqa: E402
from hold import StationHold  # noqa: E402


def test_the_example_holds_station_through_its_sensors():
    tank = Tank("bluerov2", start=(0.0, 0.0, -7.0), seconds=40.0, task=HoldStation(), sensed=True)
    report = tank.run(StationHold())
    assert report.score > 0.8, str(report)
    assert abs(report.final["depthM"] - 7.0) < 0.1


def test_a_target_depth_is_reached_and_scored():
    controller = StationHold()
    controller.tune("depthM", 9.0)
    tank = Tank("bluerov2", seconds=60.0, task=ReachDepth(9.0, tolerance_m=0.15))
    report = tank.run(controller)
    assert report.score > 0.9, str(report)
    assert abs(report.final["depthM"] - 9.0) < 0.15


def test_stepping_it_yourself_like_a_learner():
    tank = Tank("bluerov2", seconds=5.0, task=HoldStation(), sensed=False)
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
