"""The net of light on the bottom, made from the sea that is actually running.

The painted texture this replaces could not be wrong, because it was not a
claim about anything. This is a claim, so it is checked: against a flat calm,
against depth, against wavelength, and against the one thing a caustic must do
— conserve the light it moves around.
"""

from __future__ import annotations

import numpy as np
import pytest

import caustics
import sea_state


def swell(height=1.0, period=8.0, heading=0.0, seed=3):
    return sea_state.SeaState(significant_height_m=height, peak_period_s=period,
                              heading_deg=heading, seed=seed)


def test_a_flat_calm_throws_no_net():
    """No waves, no focusing — the bottom is evenly lit, not patterned."""
    lit = caustics.net(sea_state.SeaState(0.0), across=40.0, depth=8.0)
    assert np.allclose(lit, 1.0), (lit.min(), lit.max())


def test_no_sea_at_all_is_the_same_as_a_flat_one():
    assert np.allclose(caustics.net(None, 40.0, 8.0), 1.0)


def test_a_sea_throws_a_net():
    lit = caustics.net(swell(), across=40.0, depth=6.0)
    assert lit.std() > 0.05, lit.std()
    assert lit.max() > 1.2, lit.max()


def test_the_light_is_moved_around_and_not_created():
    """A caustic redistributes sunlight. Averaged over a patch many waves
    wide it has to come back to about what it started with, or the seabed is
    being lit by a second sun that nobody switched on."""
    for depth in (2.0, 4.0, 8.0):
        lit = caustics.net(swell(height=0.6), across=120.0, depth=depth,
                           size=384)
        assert lit.mean() == pytest.approx(1.0, abs=0.25), (depth, lit.mean())


def test_it_sharpens_to_a_focus_and_then_washes_out():
    """The shape a caustic actually has with depth.

    Near the surface the surface is barely bent and the net is faint. It
    sharpens as rays converge, reaches its hardest around the depth where the
    chop focuses, and then goes soft again as the sun's own half-degree width
    smears it across more than a wavelength. Contrast rising for ever was the
    first model's answer and it is the wrong shape: it would put a harder net
    on a reef at sixty metres than on one at three.
    """
    sea = swell()
    contrast = {d: float(caustics.net(sea, across=60.0, depth=float(d),
                                      size=256).std())
                for d in (1, 6, 25, 120)}
    assert contrast[1] < contrast[6] < contrast[25], contrast
    assert contrast[120] < contrast[25], contrast


def test_the_sun_is_what_washes_it_out():
    """Take the sun's width away and the net never softens — which is how the
    missing term was found in the first place."""
    sea = swell()
    was = caustics.SUN_HALF_ANGLE
    try:
        caustics.SUN_HALF_ANGLE = 0.0
        hard = float(caustics.net(sea, 60.0, 120.0, size=256).std())
    finally:
        caustics.SUN_HALF_ANGLE = was
    soft = float(caustics.net(sea, 60.0, 120.0, size=256).std())
    assert soft < hard, (soft, hard)


def test_a_long_swell_throws_a_coarser_net_than_a_chop():
    """Wavenumber enters squared, so the scale of the net follows the sea."""

    def grain(sea):
        lit = caustics.net(sea, across=60.0, depth=6.0, size=256)
        # How fast it changes from one texel to the next: fine nets change fast.
        return float(np.abs(np.diff(lit, axis=1)).mean())

    chop = grain(swell(height=0.6, period=3.0))
    long_swell = grain(swell(height=0.6, period=12.0))
    assert chop > long_swell, (chop, long_swell)


def test_it_moves_with_time():
    a = caustics.net(swell(), across=40.0, depth=6.0, seconds=0.0)
    b = caustics.net(swell(), across=40.0, depth=6.0, seconds=1.5)
    assert not np.allclose(a, b)


def test_it_travels_with_the_vehicle():
    here = caustics.net(swell(), across=40.0, depth=6.0, middle=(0.0, 0.0))
    there = caustics.net(swell(), across=40.0, depth=6.0, middle=(500.0, 0.0))
    assert not np.allclose(here, there)


def test_it_stays_finite_and_bounded_in_a_heavy_sea():
    """Counting where light lands cannot produce an infinity the way solving
    a Jacobian can — there is only ever so much light. Checked anyway, in the
    roughest sea anybody would fly in."""
    lit = caustics.net(swell(height=3.0, period=5.0), across=40.0, depth=20.0)
    assert np.isfinite(lit).all()
    assert lit.max() < 40.0, lit.max()
    assert lit.min() >= 0.0


def test_the_texture_keeps_the_shape_and_drops_the_strength():
    """Two seas of different roughness must come out at the same average
    brightness, because how bright the caustics are is set by the sunlight and
    what the texture carries is only the pattern."""
    calm = caustics.as_texture(caustics.net(swell(height=0.3), 60.0, 6.0))
    rough = caustics.as_texture(caustics.net(swell(height=1.5), 60.0, 6.0))
    assert abs(float(calm.mean()) - float(rough.mean())) < 12.0, (
        calm.mean(), rough.mean())
    assert float(rough.std()) > float(calm.std())


def test_the_texture_is_eight_bit_and_whole():
    lit = caustics.net(swell(), 40.0, 6.0)
    got = caustics.as_texture(lit)
    assert got.dtype == np.uint8
    assert got.shape == lit.shape


def test_the_texture_does_not_darken_the_ground_it_is_laid_on():
    """A caustic moves light about; it does not remove any.

    The material multiplies the ground by twice this texture's grey, so the
    texture's mean has to come out at a half whatever the net is doing.
    Normalising before clipping threw the bright tail away and left a mean
    below a half, which multiplied the whole seabed by less than one — the
    reef went dark and it looked like an exposure fault.
    """
    for height in (0.4, 1.2, 3.0):
        lit = caustics.net(swell(height=height), 90.0, 6.0, size=192)
        got = caustics.as_texture(lit).astype(float) / 255.0
        assert float(got.mean()) == pytest.approx(0.5, abs=0.02), (
            height, got.mean())
