"""The metric that measures distance rather than guessing it from image rows.

Two earlier versions of this reported faults that did not exist, so the parts
that can be wrong quietly — where the camera is, and how far the seabed is
from it — are checked against geometry somebody can work out by hand.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib

import numpy as np
import pytest

_loader = importlib.machinery.SourceFileLoader(
    "cue", str(pathlib.Path(__file__).resolve().parent / "cue"))
_spec = importlib.util.spec_from_loader("cue", _loader)
cue = importlib.util.module_from_spec(_spec)
_loader.exec_module(cue)


def flat(depth: float = -10.0, n: int = 201):
    """A seabed at one depth, so distances can be worked out with a triangle."""
    return np.full((n, n), depth, dtype="float32")


def test_a_ray_along_a_flat_bottom_is_never_further_than_the_geometry_allows():
    """A camera three metres up, looking level: the floor comes in at an angle.

    Straight down the middle of the frame the ray is horizontal and never
    meets a flat floor at all, so the middle column must be open water. The
    bottom of the frame must hit, and close.
    """
    grid = flat(-10.0)
    far = cue.distances((0.0, 0.0, -7.0), (24.0, 0.0, -7.0), grid, 1000.0,
                        64, 36)
    middle = far[18, 32]
    assert np.isnan(middle), middle
    assert not np.isnan(far[-1, 32]), "the bottom of the frame must find ground"
    assert far[-1, 32] < 40.0, far[-1, 32]


def test_further_down_the_frame_is_nearer_ground():
    """The one assumption the old metric made, now checked instead of assumed."""
    grid = flat(-10.0)
    far = cue.distances((0.0, 0.0, -7.0), (24.0, 0.0, -7.0), grid, 1000.0,
                        64, 36)
    column = far[:, 32]
    seen = column[~np.isnan(column)]
    assert len(seen) > 5
    assert np.all(np.diff(seen) <= 0.5), seen


def test_every_hit_lands_on_the_floor_it_was_traced_against():
    """The check that catches a wrong ray, a wrong lens or a wrong up-vector.

    Whatever distance comes back, walking that far along the pixel's own
    direction has to arrive at the height the seabed actually is. Asserting
    the distance against a triangle drawn from the distance proves nothing;
    this puts the answer back into the world and looks at where it lands.
    """
    grid = flat(-10.0)
    eye, look, wide, tall = (0.0, 0.0, -7.0), (100.0, 0.0, -7.0), 48, 27
    far = cue.distances(eye, look, grid, 1000.0, wide, tall)

    # The same directions the tracer builds, rebuilt here from the lens.
    ahead = np.array(look) - np.array(eye)
    ahead = ahead / np.linalg.norm(ahead)
    right = np.cross(ahead, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, ahead)
    hw = (cue.APERTURE_MM / 2.0) / cue.FOCAL_LENGTH_MM
    ht = hw * tall / wide
    sx = (np.arange(wide) + 0.5) / wide * 2 - 1
    sy = 1 - (np.arange(tall) + 0.5) / tall * 2
    dirs = (ahead + right * sx[None, :, None] * hw + up * sy[:, None, None] * ht)
    dirs /= np.linalg.norm(dirs, axis=2, keepdims=True)

    hit = ~np.isnan(far)
    assert hit.sum() > 50
    z = np.array(eye)[2] + dirs[..., 2][hit] * far[hit]
    assert np.allclose(z, -10.0, atol=cue.STEP_M * 2), (z.min(), z.max())


def test_looking_up_finds_nothing():
    grid = flat(-10.0)
    far = cue.distances((0.0, 0.0, -7.0), (24.0, 0.0, -1.0), grid, 1000.0,
                        32, 18)
    assert np.isnan(far).mean() > 0.5, np.isnan(far).mean()


def test_a_wall_ahead_is_found_at_its_own_distance():
    grid = flat(-10.0)
    # Ground rises to the surface beyond fifty metres: rows are south to north,
    # columns west to east, and the camera looks along +x.
    across, n = 1000.0, grid.shape[0]
    x = (np.arange(n) / (n - 1)) * across - across / 2
    rises = x > 50.0
    grid[:, rises] = 0.0
    # Where the wall actually starts, which is the first cell past fifty and
    # not fifty: this grid is five metres a cell, and a metric that is right
    # to the cell is right.
    wall = float(x[rises][0])
    far = cue.distances((0.0, 0.0, -7.0), (100.0, 0.0, -7.0), grid, 1000.0,
                        9, 9)
    # The middle row looks level, so it can only meet the wall — the rows
    # below it are pointed at the floor and find that first, which is not a
    # fault and is why the whole frame's minimum says nothing.
    level = far[4, 4]
    assert level == pytest.approx(wall, abs=cue.STEP_M * 2), (level, wall)
    assert far[-1, 4] < level, (far[-1, 4], level)


def test_the_floor_is_read_at_the_right_place():
    """Rows south to north, columns west to east — off by a transpose and every
    distance in every place would be wrong in a way no frame would show."""
    grid = np.zeros((101, 101), dtype="float32")
    grid[100, 0] = -42.0  # north-west corner
    got = cue.floor_at(grid, 1000.0, np.array([-500.0]), np.array([500.0]))
    assert float(got[0]) == -42.0, got


def test_bands_come_back_in_order_and_only_where_there_is_seabed():
    frame = np.zeros((40, 40, 3), dtype="float32")
    frame[..., 1] = 0.5
    frame[..., 0] = 0.4
    far = np.full((40, 40), np.nan)
    far[:20, :] = 1.0
    far[20:, :] = 40.0
    got = cue.cue(frame, far)
    assert got is not None
    assert [b["fromM"] for b in got["bands"]] == sorted(
        b["fromM"] for b in got["bands"])
    assert got["seabed"] == 1.0


def test_open_water_alone_says_so_rather_than_inventing_a_number():
    frame = np.zeros((40, 40, 3), dtype="float32")
    assert cue.cue(frame, np.full((40, 40), np.nan)) is None


def test_the_water_alone_is_the_ratio_between_the_two_flights():
    """A pale reef and a failed medium are the same saturation. Not the same
    ratio: with the medium off the reef is whatever it is, and dividing one
    by the other leaves the water."""
    tall, wide = 40, 40
    far = np.full((tall, wide), np.nan)
    far[:20, :] = 12.0
    far[20:, :] = 100.0

    # A reef whose near half is pale and far half is vivid — the opposite of
    # what the medium does, so a saturation reading would be misled.
    dry = np.zeros((tall, wide, 3), dtype="float32")
    dry[:20] = [0.60, 0.62, 0.61]
    dry[20:] = [0.20, 0.55, 0.40]
    # Water that takes red fastest, applied to both halves.
    near_left, far_left = (0.80, 0.95, 0.92), (0.20, 0.70, 0.60)
    wet = dry.copy()
    wet[:20] *= near_left
    wet[20:] *= far_left

    told = cue.against(wet, dry, far)
    assert told is not None and len(told) == 2
    # Normalised on the near band, so it reads one there by construction.
    assert told[0]["survives"] == [1.0, 1.0, 1.0], told[0]
    # And the far band is how much faster the far field went.
    want = [round(f / n, 3) for f, n in zip(far_left, near_left)]
    assert told[1]["survives"] == pytest.approx(want, abs=0.002), (
        told[1], want)
    # Red must go fastest of the three.
    assert told[1]["survives"][0] < told[1]["survives"][1]


def test_a_uniform_medium_reads_flat():
    """No falloff in, no falloff out."""
    far = np.full((40, 40), np.nan)
    far[:20, :] = 12.0
    far[20:, :] = 100.0
    dry = np.full((40, 40, 3), 0.5, dtype="float32")
    wet = dry * 0.4
    told = cue.against(wet, dry, far)
    assert all(b["survives"] == [1.0, 1.0, 1.0] for b in told), told


def test_the_fit_recovers_a_medium_it_was_given():
    """Make a frame out of a known transmission and veil, and get them back.

    This is the check that matters: the whole point of the fit is to say which
    of the two terms is wrong when a picture looks grey, and a fit that cannot
    recover a medium somebody planted is no use for that.
    """
    rng = np.random.default_rng(7)
    tall, wide = 60, 60
    far = np.full((tall, wide), np.nan)
    far[:30, :] = 12.0
    far[30:, :] = 50.0

    # A reef of many different surfaces, which is what lets a line be drawn.
    dry_lin = rng.uniform(0.02, 0.6, size=(tall, wide, 3)).astype("float64")
    trans = {12.0: np.array([0.60, 0.85, 0.80]),
             50.0: np.array([0.10, 0.45, 0.38])}
    veil = {12.0: np.array([0.02, 0.05, 0.06]),
            50.0: np.array([0.09, 0.20, 0.23])}
    wet_lin = np.zeros_like(dry_lin)
    for d in (12.0, 50.0):
        where = far == d
        wet_lin[where] = dry_lin[where] * trans[d] + veil[d]

    # Back through the transfer curve, because that is what a PNG holds.
    def encode(x):
        return np.where(x <= 0.0031308, x * 12.92,
                        1.055 * np.power(np.clip(x, 0, None), 1 / 2.4) - 0.055)

    got = cue.fit(encode(wet_lin), encode(dry_lin), far)
    assert len(got) == 2
    for band, d in zip(got, (12.0, 50.0)):
        assert band["transmission"] == pytest.approx(
            list(np.round(trans[d], 3)), abs=0.02), (band, d)
        assert band["veil"] == pytest.approx(
            list(np.round(veil[d], 4)), abs=0.01), (band, d)


def test_the_fit_will_not_guess_from_one_surface():
    """A band of one albedo is a single point: no line through it, and saying
    so is better than returning the slope of noise."""
    far = np.full((60, 60), 12.0)
    dry = np.full((60, 60, 3), 0.4, dtype="float64")
    got = cue.fit(dry * 0.5 + 0.1, dry, far)
    assert got and got[0]["transmission"] == [None, None, None], got
