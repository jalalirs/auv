"""The ride: effort, attitude and line-keeping beside the score."""

import math

import numpy as np

from tasks import task_for
from tasks.ride import Ride, distance_to


def test_distance_to_a_polyline_is_to_its_nearest_segment():
    line = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    assert math.isclose(distance_to(line, [5.0, 2.0]), 2.0)
    assert math.isclose(distance_to(line, [12.0, 5.0]), 2.0)
    assert math.isclose(distance_to(line, [-3.0, 4.0]), 5.0)


def test_effort_and_attitude_are_time_weighted():
    ride = Ride()
    for k in range(11):
        ride.step(k * 0.1, [0, 0, -5], [0.5, -0.5, 1.0, 0.0], attitude=(math.radians(10), 0.0))
    said = ride.said()
    assert math.isclose(said["effort"]["meanShare"], 0.5)
    assert said["effort"]["peakShare"] == 1.0 and said["effort"]["flatOutShare"] == 1.0
    assert math.isclose(said["rollDeg"]["typical"], 10.0) and said["pitchDeg"]["worst"] == 0.0
    assert "offLine" not in said


def test_off_the_line_counts_only_once_the_vehicle_has_come_onto_it():
    ride, line = Ride(), (np.array([[0.0, 0.0], [100.0, 0.0]]), 0.0)
    # Getting there from 20 m away is not being off the line ...
    for k in range(10):
        ride.step(k, [0.0, 20.0 - 2.0 * k, -5], [0.1], line=line)
    # ... then on it for ten seconds and 3 m off for five.
    for k in range(10, 20):
        ride.step(k, [k, 0.2, -5], [0.1], line=line)
    for k in range(20, 25):
        ride.step(k, [k, 3.0, -5], [0.1], line=line)
    off = ride.said()["offLine"]
    assert off["secondsOff"] == 5.0
    assert off["worstM"] == 3.0
    assert off["secondsOnTheLine"] >= 14.0


def test_a_transect_says_its_ride_in_its_result():
    task = task_for({"kind": "transect", "lengthM": 20.0}, [0.0, 0.0, -5.0], 0.0)
    for k in range(40):
        task.step(k * 0.5, [k * 0.5, 0.0, -5.0], 0.0, -10.0, [0.3, 0.3], attitude=(0.0, math.radians(2)))
    ride = task.result()["ride"]
    assert ride["offLine"]["secondsOff"] == 0.0
    assert math.isclose(ride["pitchDeg"]["typical"], 2.0, abs_tol=1e-6)


def test_the_ride_stops_when_the_task_is_done():
    task = task_for({"kind": "transect", "lengthM": 5.0}, [0.0, 0.0, -5.0], 0.0)
    for k in range(40):
        x = min(k * 0.5, 6.0)
        task.step(k * 0.5, [x, 0.0, -5.0], 0.0, -10.0, [0.4] if not task.done else [0.0])
    assert task.done
    ride = task.result()["ride"]
    assert ride["seconds"] < 10.0, ride
    assert abs(ride["effort"]["meanShare"] - 0.4) < 1e-6, ride
