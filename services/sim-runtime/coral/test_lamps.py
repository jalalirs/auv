"""Which way a lamp points.

A rect light faces its own -Z. Aiming one meant a swing about Z and a tip
about Y, and that was wrong twice in a way the two faults hid: the tip sent a
level aim to *minus* X, so the lamps pointed behind the vehicle, and the swing
was applied before the tip, where it acts on a vector still pointing straight
down and does nothing at all — so every lamp came out aimed the same way
whatever bearing it was given.

For a lamp aimed straight down the two faults cancel. That is why the
caustics, which are a rect light pointed at the seabed, have worked since
they were written, while the lamps never have — and why the deepest place on
the platform, where the lamps are the only light there is, came back dark.
"""

from __future__ import annotations

import numpy as np
import pytest

from runner import aiming

DOWN = np.array([0.0, 0.0, -1.0])


def sent(towards):
    """Where a rect light's -Z ends up, in USD's row-vector convention."""
    return DOWN @ aiming(np.asarray(towards, dtype=float))


@pytest.mark.parametrize("towards", [
    (1.0, 0.0, 0.0),      # level, forward — the lamps' own aim
    (-1.0, 0.0, 0.0),     # level, backward
    (0.0, 1.0, 0.0),      # level, off to one side — the case the old order dropped
    (0.0, -1.0, 0.0),
    (0.0, 0.0, -1.0),     # straight down — the one case that used to work
    (0.0, 0.0, 1.0),      # straight up
    (1.0, 1.0, -1.0),     # forward and down, which is how a lamp is really set
])
def test_a_lamp_points_where_it_is_aimed(towards):
    want = np.asarray(towards, dtype=float)
    want = want / np.linalg.norm(want)
    assert np.allclose(sent(want), want, atol=1e-9), (towards, sent(want))


def test_a_level_lamp_does_not_point_backwards():
    """The fault itself, named: `tip = 90 + asin(z)` sent -Z to -X."""
    assert sent((1.0, 0.0, 0.0))[0] == pytest.approx(1.0)


def test_bearing_is_not_thrown_away():
    """Swing-then-tip acted on a vector still pointing down, so the bearing
    did nothing and every lamp came out aimed the same way."""
    assert not np.allclose(sent((1.0, 0.0, 0.0)), sent((0.0, 1.0, 0.0)))


def test_it_is_a_rotation_and_not_a_squash():
    for towards in [(1, 0, 0), (0, 1, 0), (0.3, -0.7, 0.6)]:
        R = aiming(np.asarray(towards, dtype=float))
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-9)
        assert float(np.linalg.det(R)) == pytest.approx(1.0)


def test_an_aim_of_nothing_does_not_explode():
    R = aiming(np.array([0.0, 0.0, -1.0]))
    assert np.allclose(R, np.eye(3))


# ── how bright a lamp is ─────────────────────────────────────────────────────

def test_a_lamp_is_its_own_lumens_over_its_own_face():
    """A Lambertian emitter's luminance is flux over area times pi.

    A Lumen Subsea is fifteen hundred lumens across eight centimetres, which
    is about seventy-four thousand candela a square metre. The scale it
    replaces produced a hundred and five million — four orders of magnitude
    out, because it had been tuned to make a light that was pointing behind
    the vehicle show up at all.
    """
    from runner import lamp_nits

    assert lamp_nits(1500.0, 0.08) == pytest.approx(74_603.0, rel=0.01)


def test_a_bigger_face_at_the_same_flux_is_dimmer():
    from runner import lamp_nits

    assert lamp_nits(1500.0, 0.16) == pytest.approx(
        lamp_nits(1500.0, 0.08) / 4.0, rel=1e-6)


def test_twice_the_lumens_is_twice_the_luminance():
    from runner import lamp_nits

    assert lamp_nits(3000.0, 0.08) == pytest.approx(
        2.0 * lamp_nits(1500.0, 0.08), rel=1e-9)


def test_it_does_not_divide_by_a_face_of_no_size():
    from runner import lamp_nits

    assert lamp_nits(1500.0, 0.0) > 0.0
