"""A coral surface at the scale of its polyps.

The reason a coral head reads as a blob of clay is that it is smooth, and no
amount of noise on a dome makes corallites. There is no CC0 photograph of one
to tile, so it is made.
"""

import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import corallite  # noqa: E402


@pytest.mark.parametrize("form", sorted(corallite.FORMS))
def test_every_form_makes_a_surface(form):
    height = corallite.height_for(form, pixels=256, seed=2)
    assert height.shape == (256, 256)
    assert np.isfinite(height).all()
    # Relief in the right order: a corallite is a fraction of a millimetre
    # deep, not a canyon and not a flat sheet.
    assert 0.1 < float(np.ptp(height)) < 4.0, np.ptp(height)


def test_it_is_about_zero():
    """So a material can add it to a surface without moving the surface."""
    height = corallite.height_for("massive", pixels=256)
    assert abs(float(height.mean())) < 1e-9


def test_the_corallites_are_the_size_they_are_said_to_be():
    """Counted off the surface rather than trusted: the lattice is jittered and
    the tile is sized in millimetres, and either could be wrong by a factor."""
    from scipy import ndimage

    tile, form = 40.0, "massive"
    height = corallite.height_for(form, tile_mm=tile, pixels=512, seed=5)
    # The cups are the low ground.
    low = height < height.mean()
    count = ndimage.label(low)[1]
    expected = (tile / corallite.FORMS[form]["across"]) ** 2
    assert 0.5 * expected < count < 2.0 * expected, (count, expected)


@pytest.mark.parametrize("form", ("massive", "brain"))
def test_the_tile_wraps(form):
    """A colony is covered in perhaps forty repeats of this. A seam would be
    forty seams, in a grid, which is the most obviously wrong thing a tiled
    texture can do."""
    height = corallite.height_for(form, pixels=256, seed=4)
    # The two edges must meet as well as any two neighbouring rows do inside.
    across_the_seam = np.abs(height[0, :] - height[-1, :]).mean()
    inside = np.abs(height[1:-1, :] - height[2:, :]).mean()
    assert across_the_seam < 3.0 * inside, (across_the_seam, inside)


def test_the_normals_wrap_too():
    """A tileable height field whose normals are not tileable has a seam in the
    lighting and nowhere else, which takes a while to find."""
    height = corallite.height_for("massive", pixels=256, seed=4)
    normal = corallite.normal_from(height).astype("int16")
    seam = np.abs(normal[0, :, :2] - normal[-1, :, :2]).mean()
    inside = np.abs(normal[1:-1, :, :2] - normal[2:, :, :2]).mean()
    assert seam < 3.0 * inside, (seam, inside)


def test_a_normal_map_is_unit_length_and_points_out():
    height = corallite.height_for("massive", pixels=128)
    normal = corallite.normal_from(height).astype("float32") / 255.0 * 2.0 - 1.0
    assert float(np.linalg.norm(normal, axis=-1).mean()) == pytest.approx(1.0, abs=0.02)
    assert (normal[..., 2] > 0).all(), "a surface normal cannot point into the surface"


def test_a_form_nobody_has_described_is_refused():
    """Rather than handed a default. A sea fan's surface is spicules and
    standing polyps, which is a different thing and is not this."""
    with pytest.raises(KeyError):
        corallite.height_for("fan")
