"""A sea of a stated height and period.

The waves were four trains somebody chose: fixed lengths, fixed heights, the
same sea every day. Enough to stop the surface being a sheet of glass and not a
sea state — it could not be told that today is half a metre and Thursday is two,
and it could not be driven by a measurement.
"""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sea_state import SeaState  # noqa: E402


def significant_of(sea, n=4000, seed=1):
    """Four times the standard deviation, which is what significant means."""
    draw = np.random.RandomState(seed)
    where = draw.uniform(-300.0, 300.0, (n, 2))
    heights = np.array([sea.height_at(float(x), float(y), 0.0) for x, y in where])
    return 4.0 * float(heights.std())


def test_the_sea_is_the_height_it_was_asked_for():
    """The whole point: a buoy says 1.5 m and the surface is 1.5 m."""
    for asked in (0.4, 1.5, 3.0):
        sea = SeaState(asked, 7.0, 0.0, seed=3)
        got = significant_of(sea)
        assert abs(got - asked) < 0.15 * asked, f"asked {asked}, got {got:.2f}"


def test_a_flat_calm_is_flat():
    sea = SeaState(0.0, 7.0, 0.0, seed=3)
    assert sea.flat
    assert sea.height_at(10.0, 20.0, 5.0) == 0.0


def test_the_sea_disperses():
    """Each component travels at its own speed, so the surface is not a texture
    sliding past. A sea where everything moves together reads as wallpaper."""
    sea = SeaState(1.5, 7.0, 0.0, seed=3)
    speeds = {round(math.sqrt(9.81 / (w * w / 9.81)), 3) for _, w, _, _ in sea.waves}
    assert len(speeds) > 5, f"only {len(speeds)} distinct speeds"


def test_the_water_moves_under_the_waves_and_stops_moving_with_depth():
    """Orbital velocity dies as exp(-kz).

    This is why shallow work stops when the weather comes up and why a dive at
    forty metres does not care, and it is the half of a sea state that acts on
    a vehicle rather than on a picture.
    """
    sea = SeaState(2.0, 8.0, 0.0, seed=3)
    at = [float(np.linalg.norm(sea.orbital_at(0.0, 0.0, d, 0.0)))
          for d in (0.0, 5.0, 20.0, 60.0)]
    assert at[0] > at[1] > at[2] > at[3], at
    # An eight-second sea is a hundred metres long, so half a wavelength is
    # fifty: at sixty the motion is a small fraction of the surface and not
    # zero, because the long tail of a spectrum reaches deeper than its peak
    # does. A tenth is the honest reading of that, not a twentieth — the first
    # version of this test asserted a twentieth and was wrong about the sea
    # rather than about the code.
    assert at[3] < 0.10 * at[0], f"sixty metres should be quiet: {at}"
    assert at[3] > 0.0, "and not perfectly still, which no sea is"


def test_a_sea_runs_the_way_it_is_told_to():
    """Mostly: a real sea spreads either side of its mean heading."""
    sea = SeaState(1.5, 7.0, 90.0, seed=3)
    mean = np.mean([heading for _, _, heading, _ in sea.waves])
    assert abs(math.degrees(mean) - 90.0) < 20.0, math.degrees(mean)


def test_the_same_seed_is_the_same_sea():
    a = SeaState(1.5, 7.0, 0.0, seed=11)
    b = SeaState(1.5, 7.0, 0.0, seed=11)
    assert a.height_at(3.0, 4.0, 2.0) == b.height_at(3.0, 4.0, 2.0)
