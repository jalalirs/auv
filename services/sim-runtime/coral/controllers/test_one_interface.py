"""There is one controller interface, not two that look alike.

`Observation` and `Command` were declared once in the runtime and once in the
published SDK, and the SDK's docstring promised "the interface is the
runtime's own". They had already drifted — the runtime's observation carried
the sonar and the SDK's did not, so somebody writing against what they were
given could not see the one thing a controller learns that nobody told it.

Two implementations of one idea agree until they do not, and the disagreement
looks like a finding. This is the test that makes the sentence true.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[3] / "packages" / "sdk-python"))

import coral_city  # noqa: E402
from controllers import base  # noqa: E402


def test_the_runtime_and_the_sdk_hold_the_same_classes():
    """Not equal, not equivalent: the same object, out of one file."""
    assert base.Observation is coral_city.Observation
    assert base.Command is coral_city.Command
    assert base.Parameter is coral_city.Parameter


def test_the_observation_carries_what_a_controller_has_to_see():
    """The fields that had drifted, named, so a future edit to one side
    cannot quietly drop one."""
    fields = {f.name for f in dataclasses.fields(base.Observation)}
    assert fields == {"t", "position", "velocity", "rotation", "floor",
                      "on_the_bottom", "seen", "sonar", "estimated"}


def test_a_command_can_be_a_wrench_thrusters_or_actuators():
    kinds = {f.name for f in dataclasses.fields(base.Command)}
    assert kinds == {"wrench", "thrusters", "actuators"}
    assert base.Command.nothing().is_empty() is False
    assert base.Command().is_empty() is True
    assert base.Command.wrench_of(heave=3.0).wrench[2] == pytest.approx(3.0)
    # Clipped, because a thruster command outside [-1, 1] is not a command.
    assert base.Command.thrusters_of(2.0, -2.0).thrusters.tolist() == [1.0, -1.0]
    assert base.Command.actuators_of(buoyancyCm3=180.0).actuators == {"buoyancyCm3": 180.0}


def test_a_dive_says_whether_the_position_it_hands_over_is_an_estimate():
    """A controller scored against the truth while steering on a reckoning is
    a different problem from one holding the truth, and until the interface
    was one file nothing on the runtime's side filled the field in at all."""
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import Dive

    package = HERE.parents[3] / "catalog/vehicles/bluerov2/dynamics.json"
    model = Hydrodynamics.from_package(package)
    dive = Dive({"durationSeconds": 2, "initialState": {"positionM": [0, 0, -7]}},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **d: None)
    dive.navigation = None
    assert dive.observation().estimated is False


# ── whose controller flew ────────────────────────────────────────────────────

class _Bridge:
    """Just enough of the ROS boundary to make a stack controller."""

    commands_seen = 0
    commanded = False
    stack_node = None

    def commands(self):
        return [0.0] * 8


def test_a_deployed_controller_flies_under_its_own_name():
    """Everything that arrives over ROS 2 arrives as "a stack". Two of
    somebody's controllers on one bench were both called that."""
    from controllers.external import StackController

    stack = StackController(_Bridge(), deployed="Hold the depth", slug="hold-depth")
    assert stack.flying_as() == "Hold the depth"
    assert stack.describe()["flyingAs"] == "Hold the depth"
    assert stack.describe()["slug"] == "hold-depth"


def test_a_stack_nobody_deployed_names_itself_off_its_ros_node():
    """Started by hand rather than through the platform — still not "stack"."""
    from controllers.external import StackController

    bridge = _Bridge()
    bridge.stack_node = "wall_follower"
    assert StackController(bridge).flying_as() == "wall_follower"


def test_a_stack_that_has_said_nothing_at_all_is_the_slot_it_occupies():
    from controllers.external import StackController

    assert StackController(_Bridge()).flying_as() == "stack"


def test_a_builtin_controller_is_its_own_name():
    """The helm answers the same question for every controller, so a record
    never has to know which kind it is holding."""
    from hydrodynamics import Allocator, Hydrodynamics
    from controllers import Helm

    package = HERE.parents[3] / "catalog/vehicles/bluerov2/dynamics.json"
    model = Hydrodynamics.from_package(package)
    helm = Helm(Allocator(model), 0.005)
    assert helm.flying_as() == helm.flying.name
    assert helm.describe()["flyingAs"] == helm.flying.name


def test_the_record_says_who_flew_by_name_and_not_by_slot():
    """`who_flew` is what the bench reads to attribute a result."""
    from hydrodynamics import Allocator, Hydrodynamics
    from controllers import Helm

    package = HERE.parents[3] / "catalog/vehicles/bluerov2/dynamics.json"
    model = Hydrodynamics.from_package(package)
    helm = Helm(Allocator(model), 0.005, bridge=_Bridge(),
                deployed="Hold the depth", slug="hold-depth")
    helm.steps_flown = {"stack": 900, "hold": 100}
    said = helm.who_flew()
    assert said["mostly"] == "Hold the depth"
    assert said["shares"] == {"Hold the depth": 0.9, "hold": 0.1}
