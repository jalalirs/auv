"""Past a place's own survey, the seabed is GEBCO's, and there is no step at the edge."""

import numpy as np

from runner import Seabed


def a_place_with_surroundings():
    survey = np.full((41, 41), -10.0)                    # a flat survey, 400 m across
    gebco = np.fromfunction(lambda r, c: -20.0 - 2.0 * c, (21, 21))   # deepening eastwards
    return Seabed(survey, 400.0, around=(gebco, -5000.0, -5000.0, 5000.0, 5000.0))


def test_inside_the_survey_is_the_survey():
    sb = a_place_with_surroundings()
    assert sb.under(0.0, 0.0) == -10.0
    assert np.allclose(sb.under_many(np.array([100.0, -150.0]), np.array([50.0, 0.0])), -10.0)


def test_past_the_survey_is_gebco():
    sb = a_place_with_surroundings()
    far = sb.under(3000.0, 0.0)
    assert far < -30.0 and abs(far - float(sb._beyond(np.array([3000.0]), np.array([0.0]))[0])) < 1e-9


def test_the_edge_is_blended_not_a_step():
    sb = a_place_with_surroundings()
    xs = np.linspace(150.0, 260.0, 400)
    z = sb.under_many(xs, np.zeros_like(xs))
    assert np.abs(np.diff(z)).max() < 0.5


def test_without_surroundings_nothing_changes():
    sb = Seabed(np.full((11, 11), -7.0), 100.0)
    assert sb.under(5000.0, 0.0) == -7.0
