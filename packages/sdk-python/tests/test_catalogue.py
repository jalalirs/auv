"""A hull that is not ours.

The SDK's list of vehicles is generated from this repository's catalogue at
build time, which is right for the four hulls we publish and wrong for the
fifth. A customer can publish their own vehicle to the platform — that is
what a catalogue is for — and was then told by the SDK that there was no
such vehicle.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from coral_city import Controller, vehicles
from coral_city.catalogue import a_vehicle, from_a_package

ROOT = pathlib.Path(__file__).resolve().parents[3]

A_CARD = {
    "slug": "their-hull", "name": "Their hull", "massKg": 22.0,
    "netBuoyancyN": -3.0,
    "capability": [40.0, 30.0, 50.0, 8.0, 8.0, 12.0],
    "thrusters": [{"name": "t1", "position": [0.1, 0.1, 0.0],
                   "direction": [1.0, 0.0, 0.0]}],
    "sensors": [{"kind": "dvl", "name": "/dvl/twist"}],
    "publishes": [{"topic": "/depth", "type": "std_msgs/msg/Float64"}],
    "subscribes": [{"topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}],
    "dynamics": {"massKg": 22.0},
}


def a_package(tmp_path, card=None, slug="their-hull"):
    package = tmp_path / slug
    package.mkdir(parents=True, exist_ok=True)
    (package / "vehicle.json").write_text(json.dumps(card or A_CARD))
    return package


def test_ours_still_load_without_looking_anywhere():
    assert vehicles.load("bluerov2").slug == "bluerov2"


def test_a_hull_that_is_not_ours_loads_from_its_own_package(tmp_path, monkeypatch):
    a_package(tmp_path)
    monkeypatch.setenv("CORAL_CITY_VEHICLES", str(tmp_path))
    theirs = vehicles.load("their-hull")
    assert theirs.name == "Their hull"
    assert theirs.mass_kg == 22.0
    assert theirs.accepts == ("wrench",)
    assert theirs.most[2] == 50.0


def test_a_controller_can_name_a_hull_that_is_not_ours(tmp_path, monkeypatch):
    """The check that refuses a controller its vehicle cannot fly has to be
    able to see the vehicle first."""
    a_package(tmp_path)
    monkeypatch.setenv("CORAL_CITY_VEHICLES", str(tmp_path))

    class Theirs(Controller):
        vehicle = "their-hull"
        commands = "wrench"

        def observe(self, seen):
            raise NotImplementedError

    assert Theirs().described.slug == "their-hull"


def test_a_card_with_no_capability_is_refused_rather_than_guessed(tmp_path, monkeypatch):
    """A capability the SDK worked out for itself would be a second
    implementation of the arithmetic the runtime uses to fly the thing."""
    without = {k: v for k, v in A_CARD.items() if k != "capability"}
    a_package(tmp_path, without)
    monkeypatch.setenv("CORAL_CITY_VEHICLES", str(tmp_path))
    with pytest.raises(ValueError) as raised:
        vehicles.load("their-hull")
    assert "generate_vehicles.py --package" in str(raised.value)


def test_a_vehicle_nobody_has_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("CORAL_CITY_VEHICLES", str(tmp_path))
    with pytest.raises(KeyError) as raised:
        vehicles.load("nobodys-hull")
    said = str(raised.value)
    assert "bluerov2" in said and str(tmp_path) in said


def test_with_nowhere_to_look_it_says_how_to_point_it(monkeypatch):
    monkeypatch.delenv("CORAL_CITY_VEHICLES", raising=False)
    with pytest.raises(KeyError) as raised:
        vehicles.load("nobodys-hull")
    assert "CORAL_CITY_VEHICLES" in str(raised.value)


def test_the_card_a_package_carries_is_written_by_the_runtime(tmp_path):
    """One implementation of what a vehicle can produce, and it is the
    allocator that will actually fly it."""
    package = tmp_path / "bluerov2"
    package.mkdir()
    (package / "dynamics.json").write_text(
        (ROOT / "catalog/vehicles/bluerov2/dynamics.json").read_text())
    done = subprocess.run(
        [sys.executable, str(ROOT / "packages/sdk-python/tools/generate_vehicles.py"),
         "--package", str(package)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    card = json.loads((package / "vehicle.json").read_text())
    theirs = a_vehicle(card)
    ours = vehicles.load("bluerov2")
    assert theirs.capability == pytest.approx(ours.capability)
    assert theirs.net_buoyancy_n == pytest.approx(ours.net_buoyancy_n)
