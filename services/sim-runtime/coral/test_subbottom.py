"""The sub-bottom profiler, against what makes a section: boundaries that echo
by their contrast, and sound spent with depth and frequency."""

import numpy as np

from systems.subbottom import GROUND, trace


def test_the_seabed_echoes_and_each_boundary_below_it_does():
    rng = np.random.default_rng(0)
    column = [{"material": "sand", "thicknessM": 2.0}, {"material": "silt", "thicknessM": 6.0},
              {"material": "limestone"}]
    t = trace(column, 5.0, 0.2, 40.0, 400, rng, grain=0.0)
    z = np.linspace(0, 40, 400)
    peak = lambda d: t[np.argmin(np.abs(z - d))]      # noqa: E731
    assert peak(0.0) > peak(1.0) * 3, "the seabed"
    assert peak(2.0) > peak(1.0) * 1.5, "sand over silt"
    assert peak(8.0) > peak(5.0) * 1.5, "silt over limestone"


def test_higher_frequencies_do_not_reach_as_deep():
    rng = np.random.default_rng(0)
    column = [{"material": "sand", "thicknessM": 10.0}, {"material": "limestone"}]
    low = trace(column, 2.0, 0.2, 40.0, 400, np.random.default_rng(0), grain=0.0)
    high = trace(column, 9.0, 0.2, 40.0, 400, np.random.default_rng(0), grain=0.0)
    z = np.linspace(0, 40, 400)
    at = np.argmin(np.abs(z - 10.0))
    assert low[at] > 3 * high[at]


def test_limestone_echoes_harder_than_silt_from_sand():
    z = lambda k: GROUND[k][0] * GROUND[k][1]          # noqa: E731
    r = lambda a, b: abs((z(b) - z(a)) / (z(b) + z(a)))  # noqa: E731
    assert r("sand", "limestone") > r("sand", "silt")
