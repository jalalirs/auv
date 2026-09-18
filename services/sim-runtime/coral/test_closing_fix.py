"""How far out the vehicle was when it came up.

The number the whole industry judges a dive's navigation by, free here because
the simulator knows both where the vehicle is and where it thinks it is, and
not recorded until now. What was recorded was the drift at the end of the dive,
buried among a dozen other fields — and drift wherever the vehicle happened to
stop is not the same statement, because a fix only exists at the surface.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from navigation import Navigation


def a_navigator(began_at=(0.0, 0.0, -5.0)):
    return Navigation(began_at=np.array(began_at, dtype=float), suite={})


def test_it_says_how_far_out_the_vehicle_was():
    nav = a_navigator()
    nav.believed = np.array([10.0, 0.0, -5.0])
    said = nav.closing_fix(np.array([13.0, 4.0, -5.0]), at_surface=True)
    assert abs(said["errorM"] - 5.0) < 0.01, said
    assert said["atSurface"] is True


def test_a_dive_that_ended_on_the_bottom_has_no_fix():
    """It still has an error. It does not have a fix, and says which."""
    nav = a_navigator()
    nav.believed = np.array([10.0, 0.0, -20.0])
    said = nav.closing_fix(np.array([12.0, 0.0, -20.0]), at_surface=False)
    assert said["errorM"] > 0
    assert said["atSurface"] is False


def test_the_error_is_given_against_the_distance_run():
    """A hundred metres out after ten kilometres is a good day.

    The same hundred metres after two hundred is a broken compass, and a number
    without the distance beside it cannot tell those apart.
    """
    nav = a_navigator()
    nav.travelled = 1000.0
    nav.believed = np.array([0.0, 0.0, -5.0])
    said = nav.closing_fix(np.array([20.0, 0.0, -5.0]), at_surface=True)
    assert abs(said["shareOfDistance"] - 0.02) < 0.001, said
    assert abs(said["overM"] - 1000.0) < 0.1


def test_a_vehicle_that_has_not_moved_is_not_divided_by_zero():
    nav = a_navigator()
    nav.travelled = 0.0
    said = nav.closing_fix(np.array([0.0, 0.0, -5.0]), at_surface=True)
    assert said["shareOfDistance"] is None
