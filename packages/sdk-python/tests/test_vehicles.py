import pytest

from coral_city import Controller, vehicles


def test_the_catalogue_is_described():
    names = {v.slug for v in vehicles.all()}
    assert {"bluerov2", "bluerov2-heavy", "remus-100"} <= names


def test_the_bluerov2_takes_a_wrench_and_thrusters_and_can_lift():
    v = vehicles.load("bluerov2")
    assert set(v.accepts) == {"wrench", "thrusters"}
    assert len(v.thrusters) == 6
    assert v.capability[2] > 50.0
    assert "dvl" in v.carries


def test_a_remus_takes_only_its_propeller():
    v = vehicles.load("remus-100")
    assert v.accepts == ("thrusters",)

    class Wrenching(Controller):
        vehicle = "remus-100"
        commands = "wrench"
        needs = ("underwater_camera",)

    problems = v.check(Wrenching)
    assert any("wrench" in p for p in problems)
    assert any("underwater_camera" in p for p in problems)


def test_a_controller_for_the_wrong_vehicle_is_refused():
    class ForTheHeavy(Controller):
        vehicle = "bluerov2-heavy"

    assert vehicles.load("bluerov2").check(ForTheHeavy)
    assert not vehicles.load("bluerov2-heavy").check(ForTheHeavy)


def test_an_unknown_vehicle_says_what_there_is():
    with pytest.raises(KeyError, match="bluerov2"):
        vehicles.load("nautilus")
