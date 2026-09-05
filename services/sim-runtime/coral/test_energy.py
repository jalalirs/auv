"""What a dive costs, who decides to come home, and what flies the route."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from controllers import Observation  # noqa: E402
from energy import Battery  # noqa: E402
from hydrodynamics import Allocator, Body, Hydrodynamics  # noqa: E402
from runner import Dive  # noqa: E402

VEHICLE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"


def a_dive(seconds=120, depth=4.0, objective=None, charge=None):
    model = Hydrodynamics.from_package(VEHICLE / "dynamics.json")
    brief = {"durationSeconds": seconds, "initialState": {"positionM": [0, 0, -depth]},
             "vehiclePath": str(VEHICLE)}
    if charge is not None:
        brief["batteryCharge"] = charge
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **said: None)
    dive.floor = -12.0
    if objective is not None:
        dive.begin_task(objective)
    return dive


# ── the battery ──────────────────────────────────────────────────────────────

def test_the_battery_is_the_one_the_vehicle_declares():
    battery = Battery.of(VEHICLE)
    assert battery is not None, "the BlueROV2 package declares a pack"
    assert 250 < battery.capacity_wh < 280, "the stock pack is 14.8 V and 18 Ah"
    assert battery.hotel_w > 0 and battery.thruster_max_w > 0


def test_a_vehicle_doing_nothing_still_costs_something():
    battery = Battery.of(VEHICLE)
    idle = battery.draw(np.zeros(6), 1.0)
    assert abs(idle - battery.hotel_w) < 1e-6, "the electronics are on whether it moves or not"
    working = battery.draw(np.ones(6), 1.0)
    assert working > idle * 10, "six thrusters at full is another thing entirely"


def test_it_runs_out_and_stays_out():
    battery = Battery(capacity_wh=0.05, hotel_w=100.0, thruster_max_w=0.0)
    for _ in range(100):
        battery.draw(np.zeros(6), 1.0)
    assert battery.flat and battery.remaining_wh == 0.0
    assert battery.draw(np.ones(6), 1.0) == 0.0, "a flat battery draws nothing because it gives nothing"


def test_a_dock_puts_it_back():
    battery = Battery(capacity_wh=10.0, hotel_w=1.0, thruster_max_w=0.0, charge=0.1)
    taken = battery.charge(3600.0, 1.0)      # a kilowatt-hour an hour, for a second
    assert abs(taken - 1.0) < 1e-6 and battery.fraction > 0.19
    battery.remaining_wh = battery.capacity_wh
    assert battery.charge(3600.0, 1.0) == 0.0, "a full battery takes nothing"


def test_a_flat_battery_stops_the_dive_and_the_thrusters():
    dive = a_dive(seconds=600, charge=0.0006)     # a few seconds of hotel load
    assert dive.battery is not None
    for _ in range(int(60 / dive.dt)):
        dive.step()
        if dive.done:
            break
    assert dive.battery.flat, "it should have run itself flat"
    assert dive.ended == "battery", f"and the dive should say so, said {dive.ended!r}"
    assert float(np.max(np.abs(dive.commands))) == 0.0, "flat thrusters do nothing"


def test_what_a_dive_spends_is_on_its_result():
    dive = a_dive(seconds=20, objective={"kind": "hold-station", "seconds": 10.0})
    for _ in range(int(15 / dive.dt)):
        dive.step()
    dive.close()
    assert dive.battery.spent_wh > 0.0


# ── who flies it ─────────────────────────────────────────────────────────────

def test_the_platform_flies_a_route_it_is_given():
    dive = a_dive(seconds=400, objective={"kind": "reach", "dx": 15.0, "dy": 0.0, "radiusM": 1.5})
    assert dive.helm.flying_the_route, "a task with a route is flown by the platform"
    began = dive.position.copy()
    for _ in range(int(300 / dive.dt)):
        dive.step()
        if dive.done:
            break
    moved = float(np.linalg.norm(dive.position[:2] - began[:2]))
    assert moved > 10.0, f"it should have gone to the point, moved {moved:.1f} m"
    assert dive.ended == "achieved", f"and the dive ends when the task does, said {dive.ended!r}"
    assert dive.task.detail()["arrived"]


def test_a_dive_with_no_task_is_still_held_where_it_was_put():
    dive = a_dive(seconds=30)
    began = dive.position.copy()
    for _ in range(int(20 / dive.dt)):
        dive.step()
    assert float(np.linalg.norm(dive.position[:2] - began[:2])) < 0.5
    assert not dive.helm.flying_the_route


def test_the_waypoints_of_a_dive_are_actually_flown():
    dive = a_dive(seconds=900, objective={
        "kind": "waypoints", "radiusM": 1.5, "timeLimitS": 800.0,
        "points": [{"dx": 8, "dy": 0}, {"dx": 8, "dy": 8}, {"dx": 0, "dy": 0}]})
    for _ in range(int(800 / dive.dt)):
        dive.step()
        if dive.done:
            break
    assert dive.task.detail()["reached"] == 3, f"reached {dive.task.detail()['reached']} of 3"
    assert dive.ended == "achieved"


# ── coming home ──────────────────────────────────────────────────────────────

def seen_at(x, y, z, t=0.0):
    return Observation(t=t, position=np.array([x, y, z]), velocity=np.zeros(6),
                       rotation=np.eye(3), floor=-12.0, on_the_bottom=False)


def test_the_failsafe_leaves_a_healthy_dive_alone():
    dive = a_dive()
    dive.helm.watch_the_battery(dive.battery, dock=[0.0, 0.0, -4.0])
    assert not dive.helm.failsafe.must_come_home(seen_at(0, 0, -4)), "a full battery decides nothing"


def test_it_surfaces_when_there_is_no_dock_within_reach():
    dive = a_dive()
    dive.battery.remaining_wh = dive.battery.capacity_wh * 0.11
    dive.helm.watch_the_battery(dive.battery, dock=[900.0, 900.0, -4.0])
    dive.battery.draw(np.ones(6) * 0.8, 0.1)     # working hard, so not much time left
    assert dive.helm.failsafe.must_come_home(seen_at(0, 0, -8))
    assert dive.helm.failsafe.decided == "surface"
    assert "dock is too far" in dive.helm.failsafe.why


def test_it_goes_to_the_dock_when_the_dock_is_the_nearer_thing():
    dive = a_dive()
    dive.battery.remaining_wh = dive.battery.capacity_wh * 0.115
    dive.helm.watch_the_battery(dive.battery, dock=[3.0, 0.0, -8.0])
    dive.battery.draw(np.ones(6) * 0.8, 0.1)
    assert dive.helm.failsafe.must_come_home(seen_at(0, 0, -8))
    assert dive.helm.failsafe.decided == "dock", dive.helm.failsafe.why


def test_the_failsafe_outranks_the_hands_and_a_hand_takes_it_back():
    dive = a_dive()
    dive.battery.remaining_wh = dive.battery.capacity_wh * 0.05
    dive.helm.watch_the_battery(dive.battery, dock=None)
    dive.take_the_controls(np.array([1.0, 0, 0, 0, 0, 0]))
    dive.step()
    assert dive.helm.flying is dive.helm.failsafe, "it takes the vehicle from a hand on the keys"
    dive.take_the_controls(np.array([1.0, 0, 0, 0, 0, 0]))
    assert dive.helm.failsafe.decided is None, "and a hand on the keys takes it back"


def test_a_dive_told_to_surface_ends_when_it_gets_there():
    dive = a_dive(seconds=600, depth=3.0)
    dive.battery.remaining_wh = dive.battery.capacity_wh * 0.05
    dive.helm.watch_the_battery(dive.battery, dock=None)
    for _ in range(int(300 / dive.dt)):
        dive.step()
        if dive.done:
            break
    assert dive.helm.failsafe.decided == "surface"
    assert dive.ended in ("surfaced", "battery"), f"it ended {dive.ended!r}"


# ── picked up and put somewhere ──────────────────────────────────────────────

def test_a_vehicle_can_be_carried_and_the_record_says_so():
    dive = a_dive(seconds=60)
    dive.carry_to({"x": 40.0, "y": -25.0})
    assert abs(dive.position[0] - 40.0) < 1e-6 and abs(dive.position[1] + 25.0) < 1e-6
    assert float(np.linalg.norm(dive.velocity)) == 0.0, "it arrives stopped"
    assert dive.carried == 1 and dive.state()["carried"] == 1
    assert dive.position[2] > dive.floor, "and above the bottom, not in it"


def test_being_carried_does_not_reach_the_waypoints_on_the_way():
    dive = a_dive(seconds=600, objective={
        "kind": "waypoints", "radiusM": 1.0, "points": [{"dx": 50, "dy": 0}]})
    dive.carry_to({"x": 25.0, "y": 0.0})
    assert dive.task.detail()["reached"] == 0
    assert dive.helm.pursue.route, "and it is still steering for the point"


# ── things going wrong on purpose ────────────────────────────────────────────

def a_dive_with(failures, seconds=60):
    model = Hydrodynamics.from_package(VEHICLE / "dynamics.json")
    brief = {"durationSeconds": seconds, "initialState": {"positionM": [0, 0, -4]},
             "vehiclePath": str(VEHICLE),
             "conditions": {"kind": "constructed", "parameters": {"failures": failures}}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **said: None)
    dive.floor = -12.0
    return dive


def test_a_thruster_can_be_made_to_fail_at_a_stated_second():
    dive = a_dive_with([{"kind": "thruster", "atS": 5.0, "which": 0}])
    for _ in range(int(4.0 / dive.dt)):
        dive.step()
    assert not dive.dead_thrusters, "nothing has failed yet"
    for _ in range(int(3.0 / dive.dt)):
        dive.step()
    assert dive.dead_thrusters == {0}
    assert float(dive.commands[0]) == 0.0, "a dead thruster produces nothing whatever it is asked"
    assert dive.state()["deadThrusters"] == [0]


def test_sensors_can_drop_out_and_come_back():
    dive = a_dive_with([{"kind": "sensors", "atS": 3.0, "forS": 4.0}])
    for _ in range(int(2.0 / dive.dt)):
        dive.step()
    assert "/depth" in dive.samples(), "the sensors are fine to begin with"
    for _ in range(int(2.0 / dive.dt)):
        dive.step()
    assert "/depth" not in dive.samples(), "and quiet while they are out"
    assert dive.state().get("sensorsOut") is True
    for _ in range(int(4.0 / dive.dt)):
        dive.step()
    assert "/depth" in dive.samples(), "and back afterwards"


def test_a_gust_arrives_when_it_was_said_it_would():
    dive = a_dive_with([{"kind": "current", "atS": 2.0, "which": 0.6}])
    assert float(np.hypot(*dive.current[:2])) == 0.0
    for _ in range(int(3.0 / dive.dt)):
        dive.step()
    assert abs(float(np.hypot(*dive.current[:2])) - 0.6) < 1e-6


def test_two_runs_of_one_failure_agree():
    first = a_dive_with([{"kind": "thruster", "atS": 2.0, "which": 1}], seconds=20)
    second = a_dive_with([{"kind": "thruster", "atS": 2.0, "which": 1}], seconds=20)
    for _ in range(int(15.0 / first.dt)):
        first.step()
        second.step()
    assert np.allclose(first.position, second.position, atol=1e-12), "a failure on the clock is repeatable"


# ── another go at the same task ──────────────────────────────────────────────

def test_a_task_can_be_started_again_where_it_began():
    dive = a_dive(seconds=900, objective={"kind": "reach", "dx": 30.0, "dy": 0.0, "radiusM": 1.5})
    began = dive.position.copy()
    for _ in range(int(60 / dive.dt)):
        dive.step()
    assert float(np.linalg.norm(dive.position[:2] - began[:2])) > 5.0, "it went somewhere"
    spent = dive.battery.spent_wh
    assert spent > 0

    dive.start_again()
    assert np.allclose(dive.position, began), "it is back where the dive began"
    assert float(np.linalg.norm(dive.velocity)) == 0.0, "and stopped"
    assert dive.attempts == 2
    assert dive.battery.spent_wh == 0.0 and dive.battery.remaining_wh == dive.began_with_wh
    assert dive.task.elapsed() == 0.0 and dive.task.score() < 0.01, "the task starts from nothing"
    assert dive.state()["attempt"] == 2

    for _ in range(int(400 / dive.dt)):
        dive.step()
        if dive.task.done:
            break
    # Whether it *arrives* is a navigation question, not a retry question: it
    # flies to where it believes the point is, and where that is depends on
    # what its instruments have done to it on the way.
    assert dive.task.detail()["toGoM"] < 4.0, "it flies the leg again and ends up at the point"
    assert dive.helm.pursue.holding, "and it believes it is there"


def test_an_interactive_dive_does_not_end_when_its_task_does():
    model = Hydrodynamics.from_package(VEHICLE / "dynamics.json")
    brief = {"durationSeconds": 900, "mode": "interactive", "vehiclePath": str(VEHICLE),
             "initialState": {"positionM": [0, 0, -4]},
             "objective": {"kind": "reach", "dx": 12.0, "dy": 0.0, "radiusM": 1.5}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **said: None)
    dive.floor = -12.0
    dive.begin_task(brief["objective"])
    for _ in range(int(400 / dive.dt)):
        dive.step()
        if dive.task.done:
            break
    assert dive.task.done, "the task finished"
    for _ in range(int(20 / dive.dt)):
        dive.step()
    assert not dive.done, "the dive is still there for whoever is watching"
    assert dive.state()["taskOver"] is True
    assert dive.ended == ""


def test_a_batch_dive_still_ends_when_its_task_does():
    dive = a_dive(seconds=900, objective={"kind": "reach", "dx": 12.0, "dy": 0.0, "radiusM": 1.5})
    for _ in range(int(400 / dive.dt)):
        dive.step()
        if dive.done:
            break
    assert dive.done and dive.ended == "achieved", "nobody is watching a batch dive"
