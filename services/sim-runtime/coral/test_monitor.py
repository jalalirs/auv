"""Working a grid cell to a standard something can be reconstructed from.

A survey scores the ground it passed over, and a run that covers every square
metre from the wrong height or too fast for the shutter scores full marks for
imagery no photogrammetry will close. A monitoring programme cannot use that.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tasks import task_for  # noqa: E402

CAMERA = {"focalLengthMm": 21, "widthPx": 1280, "heightPx": 720}


def a_task(colonies=None, **objective):
    said = {"kind": "monitor", "widthM": 8.0, "heightM": 4.0,
            "altitudeM": 4.0, "altitudeBandM": 0.5, "speedMs": 0.3, "timeLimitS": 600.0}
    said.update(objective)
    return task_for(said, np.array([0.0, 0.0, -10.0]), 0.0,
                    camera=CAMERA, colonies=colonies)


def fly_over(task, points, altitude=4.0, speed=0.2, t0=0.0):
    """Pass over a line of places at a given altitude and speed."""
    t = t0
    for x, y in points:
        position = np.array([x, y, -10.0])
        task.step(t, position, 0.0, position[2] - altitude, [0.0])
        t += max(1e-3, 1.0 / max(1e-6, speed)) if False else 1.0
    return t


def test_ground_covered_well_is_usable():
    task = a_task()
    # Straight down the middle of the cell, on altitude, slowly.
    fly_over(task, [(x * 0.2, -2.0) for x in range(41)], altitude=4.0)
    assert task.detail()["fractionSeen"] > 0.9
    assert task.detail()["fractionUsable"] > 0.9
    assert task.score() > 0.9


def test_ground_covered_from_the_wrong_height_is_covered_and_useless():
    """The whole point: it went everywhere, and none of it can be used."""
    task = a_task()
    fly_over(task, [(x * 0.2, -2.0) for x in range(41)], altitude=8.0)
    assert task.detail()["fractionSeen"] > 0.9, "it covered the ground"
    assert task.detail()["fractionUsable"] == 0.0, "and not a frame of it is usable"
    assert task.score() == 0.0
    assert task.detail()["stepsTooHigh"] > 0
    assert task.detail()["stepsTooFast"] == 0


def test_ground_covered_too_fast_is_smeared():
    task = a_task()
    t = 0.0
    for i in range(41):
        position = np.array([i * 2.0, -2.0, -10.0])   # two metres per step, far over the limit
        task.step(t, position, 0.0, position[2] - 4.0, [0.0])
        t += 1.0
    assert task.detail()["stepsTooFast"] > 0
    assert task.detail()["fractionUsable"] < task.detail()["fractionSeen"]


def test_the_reason_it_was_unusable_is_kept_apart():
    """A cell that came back at forty per cent is a different problem
    depending on which of these is large, and re-flying it blind wastes a
    season."""
    high = a_task()
    fly_over(high, [(x * 0.2, -2.0) for x in range(41)], altitude=8.0)
    assert high.detail()["stepsTooHigh"] > 0 and high.detail()["stepsTooFast"] == 0


def test_it_reports_the_colonies_it_actually_imaged():
    colonies = [[1.0, -2.0], [5.0, -2.0], [50.0, 50.0]]   # the third is outside the cell
    task = a_task(colonies=colonies)
    assert task.detail()["coloniesInCell"] == 2, "only what is in the cell"
    fly_over(task, [(x * 0.2, -2.0) for x in range(41)], altitude=4.0)
    assert task.detail()["coloniesImaged"] == 2

    # And a pass at the wrong height images none of them.
    missed = a_task(colonies=colonies)
    fly_over(missed, [(x * 0.2, -2.0) for x in range(41)], altitude=8.0)
    assert missed.detail()["coloniesImaged"] == 0


def test_a_cell_can_be_named_so_a_programme_can_file_it():
    task = a_task(cell={"widthM": 8.0, "heightM": 4.0, "name": "B7"})
    assert task.detail()["cell"] == "B7"
