"""Bioturbated mud, and the line below which rippled sand is a lie."""

import numpy as np
import pytest

import sediment


def test_it_is_mud_below_the_waves_and_sand_above():
    """Storm wave base is the line, and it is deliberately deeper than the
    fifty-odd metres of ordinary swell."""
    assert sediment.BELOW_THE_WAVES_M == pytest.approx(200.0)


def test_the_tile_wraps():
    """The ground repeats it every ten metres over eight kilometres. A seam
    is eight hundred seams."""
    made = sediment.maps_for(tile_metres=10.0, texels=256, seed=5)
    for role in ("colour", "normal", "rough", "height"):
        a = made[role].astype(float)
        left, right = a[:, 0], a[:, -1]
        top, bottom = a[0, :], a[-1, :]
        # Opposite edges are neighbours once it is laid down, so they must be
        # as alike as any two adjacent rows are.
        inside = float(np.abs(a[:, 1] - a[:, 2]).mean()) + 1.0
        assert float(np.abs(left - right).mean()) < 6 * inside, role
        assert float(np.abs(top - bottom).mean()) < 6 * inside, role


def test_there_is_no_direction_in_it():
    """The whole reason a beach texture cannot be used down here is that its
    ripples run one way. Having taken those out, the mud must not have a grain
    of its own — and the first version of the rolling noise, nine sine pairs,
    interfered into a regular diagonal corrugation."""
    made = sediment.worked_over(tile_metres=10.0, texels=512, seed=9)
    height = made["height"]
    # The power in the 2-D spectrum, gathered by direction. A ripple field is
    # a spike in one direction; mud worked over by animals is not.
    power = np.abs(np.fft.fft2(height - height.mean())) ** 2
    ky = np.fft.fftfreq(power.shape[0])[:, None]
    kx = np.fft.fftfreq(power.shape[1])[None, :]
    angle = np.arctan2(ky, kx) % np.pi
    bins = np.clip((angle / np.pi * 12).astype(int), 0, 11)
    by_direction = np.array([power[bins == b].sum() for b in range(12)])
    by_direction /= by_direction.sum()
    assert by_direction.max() < 0.16, by_direction.round(3)


def test_the_animals_actually_worked_it_over():
    """Undisturbed patches are meant to be the exception on bathyal mud."""
    made = sediment.maps_for(tile_metres=10.0, texels=512, seed=4)
    assert 0.12 < made["workedFraction"] < 0.9, made["workedFraction"]
    # And the relief is centimetres, not millimetres and not a metre.
    assert 0.02 < made["reliefM"] < 0.5, made["reliefM"]


def test_a_trail_wanders():
    """1.1 radians a metre left trails that were ruled lines: a random walk in
    heading accumulates as the square root of the number of steps."""
    assert sediment.TRAIL_TURNS >= 4.0


def test_turned_mud_is_darker_than_the_surface():
    """Surface sediment is oxidised and pale; what is under it is reduced and
    grey. A fresh trail shows because it is darker, not because it is lit."""
    assert sum(sediment.TURNED_MUD) < sum(sediment.SURFACE_MUD)


def test_the_colour_is_encoded_the_way_a_photograph_is():
    """The photographed set it stands in for is sRGB, and the material decodes
    it as sRGB. A linear number written into that slot arrives six times too
    dark, which has already cost this platform one seabed."""
    made = sediment.maps_for(tile_metres=10.0, texels=128, seed=1)
    average_linear = np.array(made["average"])
    average_written = made["colour"].reshape(-1, 3).mean(axis=0) / 255.0
    assert (average_written > average_linear).all(), (average_written, average_linear)
    back = sediment._srgb(average_linear)
    assert np.allclose(back, average_written, atol=0.03), (back, average_written)
