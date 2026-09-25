"""What ground is reef, which was the denominator under everything else."""

import numpy as np
import pytest

import zonation


def test_the_light_curve_reaches_nothing_rather_than_clamping():
    """It stopped at sixty metres with four per cent, and `np.interp` clamps
    past the end of its table — so every depth below sixty came back four per
    cent for ever. Thuwal Deep is 550 m down and was handed a coral ceiling of
    four per cent over five square kilometres."""
    deep = np.array([60.0, 100.0, 150.0, 200.0, 550.0, 1800.0])
    ceiling = np.interp(deep, zonation.DEPTH_M, zonation.COVER)
    assert ceiling[0] > 0.0
    assert ceiling[-1] == 0.0
    for below in ceiling[2:]:
        assert below == 0.0, ceiling
    # And it is monotonic from the peak down, with no step at the join.
    sampled = np.interp(np.arange(8.0, 200.0, 1.0), zonation.DEPTH_M, zonation.COVER)
    assert (np.diff(sampled) <= 1e-12).all()


def test_flat_ground_is_sand_and_not_pavement():
    """`hard` used to be `0.88 + stands / 1.5`, so flat ground was 88% rock.
    It averaged 0.85 across every site and fell below 0.2 on less than one per
    cent of Al Fahal, and zonation.cover then called 94-98% of every site reef
    habitat."""
    across = 400.0
    flat = np.full((128, 128), -12.0)
    said = zonation.describe(flat, across)
    assert said["hard"].mean() < 0.1, said["hard"].mean()
    want = zonation.cover(said, np.random.default_rng(0))
    assert (want > zonation.COVER_FLOOR).mean() < 0.05


def test_ground_with_relief_on_it_is_rock():
    """The other direction: a reef must not be called sand."""
    across = 400.0
    rows = np.arange(128)
    # Spurs and grooves, a couple of metres of relief every twenty.
    rough = -12.0 + 1.2 * np.sin(rows[:, None] * 0.6) * np.cos(rows[None, :] * 0.6)
    said = zonation.describe(rough, across)
    assert said["hard"].mean() > 0.5, said["hard"].mean()


def test_a_sensor_floor_is_not_prime_reef():
    """A quarter of Al Fahal is perfectly level at exactly 21.6 m, which is
    not seabed: it is where Sentinel-2 stopped being able to see, and
    everything past it was clipped to the limit. Under the old line that
    plateau was 88% hard and carried about 44% coral."""
    across = 600.0
    ground = np.full((160, 160), -21.6)
    # A reef in one corner, the sensor's floor everywhere else.
    rows = np.arange(40)
    ground[:40, :40] = -8.0 + 1.5 * np.sin(rows[:, None]) * np.cos(rows[None, :])
    said = zonation.describe(ground, across)
    plateau = said["hard"][80:, 80:]
    assert plateau.mean() < 0.1, plateau.mean()


def test_it_says_when_the_inference_has_stopped_discriminating():
    """A reef is a structure and a site is a box drawn around it. An inference
    that says yes to two thirds of a box is not telling reef from sand."""
    everywhere = np.full((64, 64), 0.5)
    said = zonation.is_it_all_reef(everywhere)
    assert said["believable"] is False
    assert "habitat map" in said["why"]

    # Unless somebody surveyed it, in which case it is not an inference.
    assert zonation.is_it_all_reef(everywhere, surveyed=True)["believable"] is True

    patchy = np.zeros((64, 64))
    patchy[:16, :16] = 0.5
    assert zonation.is_it_all_reef(patchy)["believable"] is True


def test_the_floor_is_not_written_twice():
    """Two copies of a threshold is how there came to be two definitions of
    cover."""
    import reef

    assert zonation.COVER_FLOOR is reef.COVER_FLOOR


def test_there_is_one_hardness_and_make_site_asks_for_it():
    """There were two, and they decided two different things from the same
    seabed: `make-site.derived_hardness` what the ground is *painted* as,
    `zonation.describe` what the coral *grows* on. A place could be drawn as
    pavement where its reef was planted on sand and nothing would disagree
    with itself.

    The one in make-site was also the one that could not be wrong: it
    normalised on the median, which maps the middle of any site to a half
    whatever the site is, so it always found about as much rock as sand. On Al
    Fahal it called 63% of the site hard, including the quarter that is a
    Sentinel-2 floor clipped flat at 21.6 m.
    """
    import importlib.machinery
    import importlib.util
    import pathlib as _p

    source = (_p.Path(__file__).resolve().parent / "make-site").read_text()
    assert 'zonation.describe(height, across)["hard"]' in source
    # And none of the old model is left behind to drift back into use.
    for gone in ("1.4826", "0.62 * spread", "def spread("):
        assert gone not in source, gone


def test_the_two_hardnesses_are_the_same_numbers():
    """Not merely both present: the same array, resampled."""
    import importlib.machinery
    import importlib.util
    import pathlib as _p

    loader = importlib.machinery.SourceFileLoader(
        "make_site", str(_p.Path(__file__).resolve().parent / "make-site"))
    spec = importlib.util.spec_from_loader("make_site", loader)
    make_site = importlib.util.module_from_spec(spec)
    loader.exec_module(make_site)

    rows = np.arange(128)
    ground = -10.0 + 1.4 * np.sin(rows[:, None] * 0.4) * np.cos(rows[None, :] * 0.4)
    across = 400.0
    painted = make_site.derived_hardness(ground, across, n=128)
    grown = zonation.describe(ground, across)["hard"]
    assert painted.shape == (128, 128)
    assert np.allclose(painted, grown, atol=1e-6)


def test_the_surf_keeps_the_crest_bare():
    """The one thing make-site's model knew that zonation's did not: the
    shallowest water is scoured whatever the shape, because a reef crest in
    the surf holds no sediment."""
    across = 400.0
    # Dead flat, which would otherwise be sand — but at a metre down.
    shallow = zonation.describe(np.full((64, 64), -1.0), across)["hard"]
    deep = zonation.describe(np.full((64, 64), -14.0), across)["hard"]
    assert shallow.mean() > 0.3, shallow.mean()
    assert deep.mean() < 0.05, deep.mean()
    assert zonation.SCOURED_ABOVE_M == pytest.approx(4.0)
