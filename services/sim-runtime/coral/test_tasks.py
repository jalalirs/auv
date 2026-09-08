"""Tasks judge trajectories; these hand them trajectories and check the judgement."""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import KINDS, task_for  # noqa: E402

START = np.array([100.0, -20.0, -5.0])


def walk(task, seconds, where, heading=0.0, floor=None, dt=0.05):
    """Hand the task a trajectory for a while. `where` sees the time since this
    walk began; the task's clock keeps running across walks, as a dive's does."""
    began = getattr(task, "_clock", 0.0)
    steps = int(round(seconds / dt))
    for k in range(steps + 1):
        local = k * dt
        task.step(began + local, where(local), heading, floor(local) if callable(floor) else floor, [0.1] * 6)
    task._clock = began + steps * dt
    return task


def test_every_kind_is_known():
    for kind in KINDS:
        task = task_for({"kind": kind}, START, 0.0)
        assert task is not None, kind
    assert task_for({}, START, 0.0) is None
    assert task_for({"kind": "juggle"}, START, 0.0) is None


def test_hold_station_scores_the_time_on_station():
    task = task_for({"kind": "hold-station", "seconds": 20, "radiusM": 0.5, "depthBandM": 0.3}, START, 0.0)
    # Half the time on station, half a metre and a half off.
    walk(task, 20, lambda t: START if t < 10 else START + np.array([1.5, 0, 0]))
    assert task.done
    assert 0.45 <= task.score() <= 0.55, task.progress()
    result = task.result()
    assert result["achieved"]["worstOffM"] == 1.5
    assert result["thrusterEffort"] == 0.1


def test_waypoints_are_reached_in_order():
    task = task_for({"kind": "waypoints", "radiusM": 1.0, "timeLimitS": 100,
                     "points": [{"dx": 5, "dy": 0}, {"dx": 5, "dy": 5}]}, START, 0.0)
    # Straight to the second point first: it does not count until the first is
    # reached. dy is to starboard, which for a heading of east is south.
    walk(task, 5, lambda t: START + np.array([5, -5, 0]))
    assert task.reached == 0
    walk(task, 5, lambda t: START + np.array([5, 0, 0]))
    assert task.reached == 1
    walk(task, 5, lambda t: START + np.array([5, -5, 0]))
    assert task.reached == 2 and task.done and task.score() == 1.0
    geometry = task.geometry()
    assert len(geometry["points"]) == 2 and geometry["points"][0]["x"] == 105.0


def test_waypoints_relative_to_the_heading():
    task = task_for({"kind": "waypoints", "points": [{"dx": 10, "dy": 0}]}, START, math.radians(90))
    point = task.points[0]
    assert abs(point[0] - START[0]) < 1e-9 and abs(point[1] - (START[1] + 10)) < 1e-9  # north, ten metres


def test_transect_counts_length_flown_in_band_on_heading():
    task = task_for({"kind": "transect", "lengthM": 20, "altitudeM": 2.0, "altitudeBandM": 0.5,
                     "headingToleranceDeg": 10}, START, 0.0)
    floor = -7.0  # two metres under a vehicle at -5
    # First half at altitude, second half a metre too high.
    walk(task, 10, lambda t: START + np.array([t * 2.0, 0, 0 if t < 5 else 1.0]), heading=0.0, floor=floor)
    assert task.done, task.progress()
    assert 0.45 <= task.score() <= 0.55, task.progress()


def test_survey_scores_the_fraction_seen():
    task = task_for({"kind": "survey", "widthM": 10, "heightM": 6, "altitudeM": 2.0, "swathM": 3.0}, START, 0.0)
    # Two passes three metres apart cover a six-metre-tall rectangle.
    def where(t):
        if t < 10:
            return START + np.array([t, -1.5, 0])
        return START + np.array([20 - t, -4.5, 0])
    walk(task, 20, where, floor=-7.0)
    assert task.score() > 0.95, task.progress()
    assert task.done


def test_return_is_home_and_surfaced():
    task = task_for({"kind": "return", "homeRadiusM": 2.0, "surfaceDepthM": 0.5}, START, 0.0)
    walk(task, 5, lambda t: START + np.array([10, 0, 0]))
    assert task.score() == 0.0
    walk(task, 5, lambda t: START)
    assert task.score() == 0.5 and not task.done
    walk(task, 5, lambda t: np.array([START[0], START[1], -0.2]))
    assert task.score() == 1.0 and task.done


def test_inspect_wants_every_side_of_the_thing():
    task = task_for({"kind": "inspect", "dx": 10, "dy": 0, "radiusM": 4.0, "bandM": 2.0},
                    START, 0.0, camera={"focalLengthMm": 21})
    target = np.array([START[0] + 10.0, START[1], START[2]])
    # One lap at the right distance, always facing the thing.
    for step in range(24):
        angle = 2 * np.pi * step / 24
        where = np.array([target[0] + 4.0 * np.cos(angle), target[1] + 4.0 * np.sin(angle), target[2]])
        facing = np.arctan2(target[1] - where[1], target[0] - where[0])
        task.step(step * 1.0, where, float(facing), None, [0.1])
    assert task.done and task.score() == 1.0, f"a full lap should see every side, got {task.score()}"

    # Half a lap sees half the sides and is not done.
    half = task_for({"kind": "inspect", "dx": 10, "dy": 0, "radiusM": 4.0}, START, 0.0)
    for step in range(12):
        angle = np.pi * step / 12
        where = np.array([target[0] + 4.0 * np.cos(angle), target[1] + 4.0 * np.sin(angle), target[2]])
        facing = np.arctan2(target[1] - where[1], target[0] - where[0])
        half.step(step * 1.0, where, float(facing), None, [0.1])
    assert 0.3 < half.score() < 0.7 and not half.done


def test_every_task_states_a_goal_a_planner_can_fly():
    """A task says what it wants; a planner works out how.

    Both halves are checked here, because the split is the point: the task must
    say something in the world's own terms, and the platform's planner must be
    able to turn that into a path. Neither half may know about the other.
    """
    from controllers import plan

    for objective in ({"kind": "waypoints"}, {"kind": "transect", "lengthM": 20},
                      {"kind": "survey", "widthM": 10, "heightM": 6},
                      {"kind": "reach", "dx": 20}, {"kind": "search", "widthM": 20, "heightM": 10},
                      {"kind": "inspect", "dx": 10}, {"kind": "revisit"},
                      {"kind": "dock", "dx": 12}, {"kind": "return"}):
        task = task_for(objective, START, 0.0, camera={"focalLengthMm": 21})
        assert task is not None, objective
        goal = task.goal()
        assert goal.get("kind"), f"{objective['kind']} says nothing about what it wants"
        route = plan.route_for(goal, believed=START, camera_half_angle=0.41)
        assert route, f"the planner cannot fly {objective['kind']}"
        for leg in route:
            assert "x" in leg and "y" in leg, f"{objective['kind']} planned a leg going nowhere"


def test_a_task_cannot_hand_over_its_own_answer():
    """The whole of item 31, as one assertion.

    A task that can name a waypoint is a task that has done the controller's
    work, and a matrix flown that way measures a line we supplied.
    """
    task = task_for({"kind": "survey", "widthM": 10, "heightM": 6}, START, 0.0)
    assert not hasattr(task, "route"), "a task is still carrying its own solution"


def test_reaching_a_point_rewards_going_directly():
    straight = task_for({"kind": "reach", "dx": 20, "dy": 0, "radiusM": 1.0}, START, 0.0)
    for step in range(41):
        walked = np.array([START[0] + step * 0.5, START[1], START[2]])
        straight.step(step * 1.0, walked, 0.0, None, [0.1])
    assert straight.done and straight.detail()["arrived"]
    assert straight.score() > 0.98, "a straight run should score nearly one"

    wandering = task_for({"kind": "reach", "dx": 20, "dy": 0, "radiusM": 1.0}, START, 0.0)
    for step in range(81):
        along = step * 0.25
        # The same point, reached by a route that weaves and straightens out.
        off = 4.0 * np.sin(along) * max(0.0, 1.0 - along / 20.0)
        wandering.step(step * 1.0, np.array([START[0] + along, START[1] + off, START[2]]),
                       0.0, None, [0.1])
    assert wandering.done and wandering.score() < straight.score(), "wandering there is worth less"


def test_a_search_is_over_when_the_thing_comes_into_view():
    task = task_for({"kind": "search", "widthM": 30, "heightM": 20, "seeM": 6.0,
                     "target": {"dx": 20.0, "dy": 0.0}}, START, 0.0,
                    camera={"focalLengthMm": 21})
    for step in range(20):
        task.step(step * 1.0, np.array([START[0] + step * 0.5, START[1], START[2]]), 0.0, None, [0.1])
    assert not task.done, "ten metres away and it has not been seen yet"
    for step in range(20, 40):
        task.step(step * 1.0, np.array([START[0] + step * 0.5, START[1], START[2]]), 0.0, None, [0.1])
    assert task.done and task.detail()["found"], "driving up to it should find it"
    assert task.score() > 0.6


def test_a_search_can_be_ended_by_a_controller_that_says_where_it_is():
    task = task_for({"kind": "search", "target": {"dx": 40.0, "dy": 0.0}}, START, 0.0)
    task.step(1.0, np.array(START, dtype=float), 0.0, None, [0.1])
    task.report([START[0] + 41.0, START[1], START[2]])
    assert task.done and task.detail()["found"], "a right answer is finding it"
    assert task.detail()["reportErrorM"] < 2.0


def test_treatment_is_a_share_of_the_colonies_that_are_there():
    colonies = [[START[0] + x, START[1] + y] for x in range(0, 10, 2) for y in range(-4, 5, 2)]
    task = task_for({"kind": "treat", "radiusM": 12.0, "reachM": 1.2, "altitudeM": 1.5},
                    START, 0.0, colonies=colonies)
    assert task.detail()["of"] == len(colonies)
    # Along the middle row only, low enough to count.
    for step in range(20):
        where = np.array([START[0] + step * 0.5, START[1], START[2]])
        task.step(step * 1.0, where, 0.0, float(START[2]) - 1.5, [0.1])
    treated = task.detail()["treated"]
    assert 0 < treated < len(colonies), f"one pass treats one row, got {treated}"
    assert 0.0 < task.score() < 1.0


def test_a_mission_is_its_stages_in_order():
    objective = {"kind": "mission", "stages": [
        {"kind": "reach", "dx": 10, "dy": 0, "radiusM": 1.0},
        {"kind": "wait", "seconds": 20.0, "reason": "charging"},
        {"kind": "reach", "dx": 0, "dy": 0, "radiusM": 1.0},
    ]}
    task = task_for(objective, START, 0.0)
    assert task.detail()["of"] == 3 and task.detail()["stage"] == 0
    for step in range(25):
        task.step(step * 1.0, np.array([START[0] + step * 0.5, START[1], START[2]]), 0.0, None, [0.1])
    assert task.detail()["stage"] == 1, "reaching the point moves it on to the wait"
    where = np.array([START[0] + 12.0, START[1], START[2]])
    for step in range(25, 45):
        task.step(step * 1.0, where, 0.0, None, [0.1])
    assert task.detail()["stage"] == 2, "the wait ends on its own"
    for step in range(45, 90):
        back = max(0.0, 12.0 - (step - 45) * 0.5)
        task.step(step * 1.0, np.array([START[0] + back, START[1], START[2]]), 0.0, None, [0.1])
    assert task.done and not task.failed(), "all three stages are done"
    assert task.score() >= 0.9 and len(task.detail()["stages"]) == 3


def test_a_mission_stops_at_the_stage_that_failed():
    objective = {"kind": "mission", "stages": [
        {"kind": "reach", "dx": 500, "dy": 0, "radiusM": 1.0, "timeLimitS": 5.0},
        {"kind": "wait", "seconds": 5.0},
    ]}
    task = task_for(objective, START, 0.0)
    for step in range(10):
        task.step(step * 1.0, np.array(START, dtype=float), 0.0, None, [0.1])
    assert task.done and task.failed(), "the mission ends with the stage that failed"
    assert task.detail()["stage"] == 0


def test_docking_is_a_miss_if_it_arrives_too_fast():
    objective = {"kind": "dock", "dx": 10, "dy": 0, "toleranceM": 0.4, "speedMs": 0.25,
                 "headingToleranceDeg": 20}
    fast = task_for(objective, START, 0.0)
    for step in range(30):
        along = step * 0.5          # half a metre a second, twice the limit
        fast.step(step * 1.0, np.array([START[0] + along, START[1], START[2]]), 0.0, None, [0.1])
    assert not fast.detail()["docked"] and fast.detail()["arrivedTooFast"] > 0

    slow = task_for(objective, START, 0.0)
    for step in range(120):
        along = min(10.0, step * 0.1)
        slow.step(step * 1.0, np.array([START[0] + along, START[1], START[2]]), 0.0, None, [0.1])
    assert slow.done and slow.detail()["docked"] and slow.score() == 1.0


def test_survey_coverage_comes_from_the_camera_footprint_when_a_camera_is_known():
    # A 21 mm lens on a 36 mm frame sees 81 degrees; two metres up that is a
    # 3.4 m footprint, so one pass along a 3 m tall rectangle covers it.
    camera = {"name": "forward", "focalLengthMm": 21}
    task = task_for({"kind": "survey", "widthM": 10, "heightM": 3, "altitudeM": 2.0, "swathM": 0.5},
                    START, 0.0, camera=camera)
    walk(task, 10, lambda t: START + np.array([t, -1.5, 0]), floor=-7.0)
    assert task.score() > 0.95, task.progress()
    assert task.detail()["swathFrom"] == "camera footprint"
    # Without a camera the declared half-metre swath sees a sixth of it.
    plain = task_for({"kind": "survey", "widthM": 10, "heightM": 3, "altitudeM": 2.0, "swathM": 0.5}, START, 0.0)
    walk(plain, 10, lambda t: START + np.array([t, -1.5, 0]), floor=-7.0)
    assert plain.score() < 0.5, plain.progress()
