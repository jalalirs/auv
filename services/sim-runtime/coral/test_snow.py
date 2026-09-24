"""Marine snow, and the one thing it must not do: follow the camera.

Backscatter that travels with the lens is a decal. What makes ROV footage
look like ROV footage is that the particles stay where they are and the
vehicle goes through them.
"""

from __future__ import annotations

import numpy as np
import pytest

import snow
import water


def test_the_count_comes_off_the_measured_one():
    """Seven hundred above half a millimetre, a power law to two — about a
    sixtieth of them, which is a number that can be drawn."""
    got = snow.per_cubic_metre()
    assert got == pytest.approx(700.0 / 64.0, rel=0.01), got


def test_dirtier_water_carries_more_of_it():
    clear = snow.per_cubic_metre(water.JERLOV["I"])
    coastal = snow.per_cubic_metre(water.JERLOV["1C"])
    harbour = snow.per_cubic_metre(water.JERLOV["9C"])
    assert clear < coastal < harbour, (clear, coastal, harbour)
    # The clearest water is the water the count was measured in.
    assert clear == pytest.approx(snow.per_cubic_metre(), rel=0.01)


def test_the_sizes_are_a_heavy_tail_starting_at_the_cut():
    drawn = snow.sizes(20000, np.random.RandomState(0))
    assert drawn.min() >= snow.SMALLEST_DRAWN_MM / 1000.0 - 1e-12
    # Mostly grains: more than half within a third again of the cut.
    small = (drawn < 1.33 * snow.SMALLEST_DRAWN_MM / 1000.0).mean()
    assert small > 0.5, small
    # And a few with some size to them.
    assert drawn.max() >= snow.LARGEST_DRAWN_MM / 1000.0 - 1e-12


def test_the_particles_stay_put_when_the_camera_moves():
    """The whole point. A particle a metre in front of the lens must be a
    metre behind it after the vehicle has gone two metres, not still in
    front."""
    field = snow.Snow(reaches_m=4.0, seed=1)
    watched = field.where()[0].copy()
    field.follow((0.0, 0.0, 0.0))
    before = field.where()[0].copy()
    field.follow((1.0, 0.0, 0.0))
    after = field.where()[0].copy()
    # It has not moved in the world, unless wrapping took it right round.
    moved = np.linalg.norm(after - before)
    assert moved < 1e-9 or moved == pytest.approx(8.0, abs=1e-6), moved
    assert watched is not None


def test_the_box_keeps_its_count_however_far_the_camera_goes():
    field = snow.Snow(reaches_m=3.0, seed=2)
    was = field.count
    for step in range(40):
        field.follow((step * 2.5, step * 1.1, -step * 0.3))
        assert field.count == was
        near = field.where() - np.array(
            [step * 2.5, step * 1.1, -step * 0.3])[None, :]
        assert np.abs(near).max() <= 3.0 + 1e-6, np.abs(near).max()


def shifted(before, after, reaches):
    """How far each particle moved, allowing for the wrap.

    A particle that leaves one face of the box comes back in at the opposite
    one, so a plain subtraction reports a whole box side for those and the
    mean of that is nonsense. The minimal image — the shortest move that
    explains the new position — is the one that is actually meant.
    """
    side = 2.0 * reaches
    return (after - before + reaches) % side - reaches


def freely(field, before):
    """Which particles the near-field guard did not have to touch.

    Anything pushed off the lens has not moved by the drift, and it should
    not have: its position is set by where the camera is, not by where the
    water went. Those are excluded rather than argued with.
    """
    near = np.linalg.norm(field.where() - field.middle[None, :], axis=1)
    was = np.linalg.norm(before - field.middle[None, :], axis=1)
    return (near > snow.NEAREST_M + 0.05) & (was > snow.NEAREST_M + 0.05)


def test_it_sinks_rather_than_rains():
    """Tens of metres a day. Over a ten-second shot that is millimetres, which
    is drift and not weather."""
    field = snow.Snow(reaches_m=4.0, seed=3)
    before = field.where().copy()
    field.drift(10.0)
    free = freely(field, before)
    fell = -shifted(before, field.where(), field.reaches)[free, 2]
    assert np.allclose(fell, snow.SINKS_M_PER_S * 10.0, atol=1e-9)
    assert 0.0 < float(fell.mean()) < 0.02, fell.mean()


def test_it_goes_where_the_water_goes():
    field = snow.Snow(reaches_m=4.0, seed=4)
    before = field.where().copy()
    field.drift(2.0, current=(0.5, 0.0, 0.0))
    free = freely(field, before)
    moved = shifted(before, field.where(), field.reaches)[free]
    assert np.allclose(moved[:, 0], 1.0, atol=1e-9), moved[:, 0].mean()


def test_there_is_a_ceiling_on_how_many_are_drawn():
    """A harbour at four metres asks for far more than is worth drawing, and
    a reef that hangs the renderer is worse than a reef with no snow in it."""
    field = snow.Snow(reaches_m=4.0, lengths=water.JERLOV["9C"], most=6000)
    assert field.asked > 6000
    assert field.count == 6000


def test_a_camera_that_has_not_moved_leaves_them_alone():
    field = snow.Snow(reaches_m=4.0, seed=5)
    before = field.where().copy()
    field.follow((0.0, 0.0, 0.0))
    assert np.allclose(field.where(), before)


def test_nothing_the_size_of_a_thumbnail():
    """A power law has no top to it. Unbounded, one draw in a few thousand
    came out at five centimetres, which at a metre from the lens is a white
    square — and there were several in every frame."""
    drawn = snow.sizes(200000, np.random.RandomState(1)) * 1000.0
    assert drawn.max() <= snow.LARGEST_DRAWN_MM + 1e-9, drawn.max()
    # And the cap is rare enough not to pile everything up on it. A quarter
    # the size is sixty-four times as many, so a couple of per cent sit on it.
    assert (drawn >= snow.LARGEST_DRAWN_MM - 1e-9).mean() < 0.05


def test_they_do_not_all_face_the_same_way():
    """Unrotated cubes present identical squares and the frame fills with
    them. It was the sameness that read as wrong more than the size."""
    field = snow.Snow(reaches_m=3.0, seed=6)
    assert field.facing.shape == (field.count, 4)
    lengths = np.linalg.norm(field.facing, axis=1)
    assert np.allclose(lengths, 1.0, atol=1e-6)
    assert field.facing.std(axis=0).min() > 0.1, field.facing.std(axis=0)


def test_nothing_sits_against_the_lens():
    field = snow.Snow(reaches_m=3.0, seed=7)
    for step in range(12):
        field.follow((step * 0.7, 0.0, 0.0))
        near = np.linalg.norm(
            field.where() - np.array([step * 0.7, 0.0, 0.0])[None, :], axis=1)
        assert near.min() >= snow.NEAREST_M - 1e-9, near.min()


def test_the_clear_half_metre_is_round_whoever_is_looking():
    """The guard is only worth anything at the point the camera is at.

    On a dive the camera is on the vehicle and the two are the same point. On
    a tour they are not: the still camera stands where the view says, and
    Thuwal Deep's lamp view put it a metre and a half under the hull. The box
    had been settled on the *vehicle*, so an eight-millimetre aggregate a
    clear half-metre from the hull was nineteen centimetres off the glass, and
    came back sixty-one pixels across.

    So following a camera has to mean following *that* camera.
    """
    hull = np.array([10.0, -4.0, -556.0])
    lens = hull + np.array([0.0, 0.0, -1.6])

    field = snow.Snow(reaches_m=3.0, seed=11)
    field.follow(hull)
    # The fault, stated: settled on the hull, the lens is not protected.
    off_the_glass = np.linalg.norm(field.where() - lens[None, :], axis=1).min()

    field.follow(lens)
    now = np.linalg.norm(field.where() - lens[None, :], axis=1).min()
    assert now >= snow.NEAREST_M - 1e-9, now
    assert now > off_the_glass


def test_less_of_it_gets_to_the_deep():
    """Marine snow is made at the top of the ocean and eaten on the way down.

    Pilskaln's aggregates were counted in the euphotic zone. Applied unchanged
    at five hundred and fifty metres they put a snowstorm in front of a
    vehicle at the density of a reef at fifteen — and the deep is exactly
    where the difference is the whole character of the frame.

    Martin et al. 1987 fitted the fall of sinking flux as (z/100) to the minus
    0.858, which at 550 m is about a fifth.
    """
    assert snow.how_much_gets_this_deep(100.0) == pytest.approx(1.0)
    assert snow.how_much_gets_this_deep(550.0) == pytest.approx(0.232, abs=0.01)
    assert snow.how_much_gets_this_deep(1000.0) < snow.how_much_gets_this_deep(550.0)

    reef = snow.per_cubic_metre(depth_m=15.0)
    deep = snow.per_cubic_metre(depth_m=550.0)
    assert deep < reef / 4.0, (reef, deep)


def test_the_curve_is_not_run_upwards_into_a_reef():
    """It is a fit to sediment traps below the euphotic zone, and it has
    nothing to say about the water a reef is in. Extrapolated up it claims
    four times the snow at ten metres, off the back of a deep-sea correction.
    """
    for shallow in (0.0, 5.0, 15.0, 40.0, 99.0, 100.0):
        assert snow.how_much_gets_this_deep(shallow) == pytest.approx(1.0)
    assert snow.per_cubic_metre(depth_m=15.0) == pytest.approx(
        snow.per_cubic_metre(depth_m=None))


def test_a_deep_box_holds_fewer_than_a_shallow_one():
    shallow = snow.Snow(reaches_m=3.0, seed=3, most=200000, depth_m=15.0)
    deep = snow.Snow(reaches_m=3.0, seed=3, most=200000, depth_m=550.0)
    assert deep.count < shallow.count / 4, (shallow.count, deep.count)
    assert deep.count > 0
