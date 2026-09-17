"""The third command form, and the vehicle it opens.

The runtime has had `actuators` on its Command since gliders were built. The
SDK had a wrench and thruster commands and nothing else, so the vehicle this
whole phase was built around was closed to exactly the people whose controllers
are supposed to be the point: somebody outside this repository could fly a
BlueROV2 and could not fly a Seaglider.
"""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coral_city import Command  # noqa: E402
from coral_city.vehicles import ALL  # noqa: E402


def the_example(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "examples" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Seen:
    """Just the one thing a sawtooth looks at."""

    def __init__(self, depth):
        self.depth = depth


def test_a_command_can_name_a_vehicles_own_actuators():
    asked = Command.actuators_of(vbdCc=-220.0, pitchM=0.02)
    assert asked.actuators == {"vbdCc": -220.0, "pitchM": 0.02}
    assert asked.wrench is None and asked.thrusters is None


def test_a_glider_says_it_takes_actuators_and_not_a_wrench():
    """A hull with no propeller takes neither of the other two, and a check
    that knew only those told the author of a glider controller that their
    vehicle accepted nothing at all."""
    glider = ALL["seaglider"]
    assert glider.accepts == ("actuators",)
    assert len(glider.thrusters) == 0
    assert glider.actuators == ("vbdCc", "pitchM", "rollM")


def test_a_glider_says_how_far_each_one_goes():
    """A controller author should not have to read the runtime to find out
    that a package declares limits and a command sends demands."""
    glider = ALL["seaglider"]
    assert glider.limits_of("vbdCc") == (-400.0, 400.0)
    low, high = glider.limits_of("pitchM")
    assert low < 0 < high


def test_a_thrusting_vehicle_still_takes_what_it_always_did():
    rov = ALL["bluerov2"]
    assert "wrench" in rov.accepts and "thrusters" in rov.accepts
    assert rov.actuators == ()


def test_the_example_can_fly_the_glider_and_not_the_rov():
    sawtooth = the_example("sawtooth").Sawtooth
    assert ALL["seaglider"].check(sawtooth) == []
    refused = ALL["bluerov2"].check(sawtooth)
    assert any("actuators" in one for one in refused), refused


def test_the_sawtooth_turns_at_both_ends_and_nowhere_else():
    """A glider that changed its mind on the way would spend its endurance
    pumping, and the pump is most of what it spends."""
    sawtooth = the_example("sawtooth").Sawtooth()
    for depth in (20.0, 150.0, 299.0):
        asked = sawtooth.observe(Seen(depth))
        assert asked.actuators["vbdCc"] < 0, f"should still be heavy at {depth} m"
    assert sawtooth.observe(Seen(301.0)).actuators["vbdCc"] > 0
    for depth in (280.0, 100.0, 16.0):
        assert sawtooth.observe(Seen(depth)).actuators["vbdCc"] > 0
    assert sawtooth.observe(Seen(14.0)).actuators["vbdCc"] < 0


def test_nose_down_to_fall_and_nose_up_to_climb():
    sawtooth = the_example("sawtooth").Sawtooth()
    falling = sawtooth.observe(Seen(100.0))
    sawtooth.falling = False
    climbing = sawtooth.observe(Seen(100.0))
    assert falling.actuators["pitchM"] * climbing.actuators["pitchM"] < 0
