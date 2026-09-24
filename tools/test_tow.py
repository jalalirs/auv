"""Towing a hull, and the two different questions a tank can answer."""

import importlib.machinery
import importlib.util
import json
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tow():
    loader = importlib.machinery.SourceFileLoader("tow", str(HERE / "tow"))
    spec = importlib.util.spec_from_loader("tow", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _model(tow, density=None):
    return tow.hydro.Hydrodynamics.from_package(
        HERE.parent / "catalog" / "vehicles" / "bluerov2" / "dynamics.json",
        density=tow.hydro.density_of(0.0, 20.0) if density is None else density)


def test_a_tow_reads_the_table_it_was_integrated_from():
    """At steady speed the carriage supplies exactly what the water takes, so
    the pull must equal D_l U + D_q U squared. Anything else is a fault in the
    water path through Body.step — restoring, damping, wrench assembly, or a
    sign in one of them."""
    tow = _tow()
    model = _model(tow)
    for speed in tow.SPEEDS:
        pulled = tow.towed(model, speed)["towedN"]
        said = tow.closed_form(model, speed)
        assert pulled == pytest.approx(said, rel=tow.OBEYS_ITSELF), (speed, pulled, said)


def test_a_release_arrives_where_the_arithmetic_says():
    """The other half, and the half that tests the integrator: under a steady
    pull the hull accelerates until drag balances it, and where it stops is
    the positive root of q U squared + l U - F. A wrong added mass, a wrong
    step or a sign error shows up as arriving at the wrong speed."""
    tow = _tow()
    model = _model(tow)
    for pull in (2.0, 8.0, 20.0, 40.0):
        run = tow.released(model, pull)
        assert run["reachedMs"] == pytest.approx(
            run["theRootMs"], rel=tow.REACHES_THE_ROOT), run
        assert run["settledInS"] is not None, run


def test_the_water_it_drags_with_it_is_in_the_mass():
    """Effective mass is the hull plus its added mass. If it were only the
    hull the release would arrive at the same speed and get there too fast,
    which is the failure this number exists to make visible."""
    tow = _tow()
    model = _model(tow)
    mass = tow.hydro.Body(model).effective_mass(1.0)[0]
    assert mass == pytest.approx(model.mass_kg + model.added_mass[0], rel=1e-9)
    assert mass > model.mass_kg


def test_a_tow_is_run_in_fresh_water():
    """A tank is tap water and the sea is not. hydrodynamics.py has said since
    it was written that the difference is more than the precision anybody
    claims for a drag coefficient."""
    tow = _tow()
    fresh = tow.hydro.density_of(0.0, 20.0)
    assert 995.0 < fresh < 1000.0, fresh
    assert fresh < tow.hydro.DENSITY_SEAWATER
    assert "density_of(0.0, 20.0)" in (HERE / "tow").read_text()


def test_the_bluff_band_is_not_judged_where_it_does_not_apply():
    """Half rho U squared C_d A is a quadratic drag with no linear term, and
    at low speed this hull's drag is mostly linear. The first run of this
    reported the vehicle OUT at 0.1 m/s and said so as though it were a
    finding."""
    tow = _tow()
    model = _model(tow)
    applies = (tow.WHERE_THE_BAND_APPLIES * model.linear_damping[0]
               / model.quadratic_damping[0])
    # Where it applies, the quadratic term really is most of the drag.
    quadratic = model.quadratic_damping[0] * applies * applies
    assert quadratic / tow.closed_form(model, applies) > 0.7
    # And that is well above the slowest speed towed, so the guard bites.
    assert applies > min(tow.SPEEDS)


def test_it_refuses_to_measure_drag_anywhere_that_is_not_a_tank(tmp_path):
    """A drag number measured over a reef is a drag number plus an unknown
    amount of terrain."""
    tow = _tow()
    place = tmp_path / "somewhere"
    place.mkdir()
    (place / "site.json").write_text(json.dumps({"name": "reef", "tow": {}}))
    with pytest.raises(SystemExit):
        tow.a_tank(place)


def test_a_flat_plate_friction_line_is_not_used():
    """The BlueROV2 is an open frame of cylinders and its drag is form drag.
    ITTC 1957 is for ship hulls where friction dominates; against this it
    would give a number ten times too small and a false pass."""
    source = (HERE / "tow").read_text()
    assert "ITTC" in source, "the wrong reference should be named and refused"
    assert "0.075" not in source, "the ITTC line is being used"


def test_the_hull_says_how_big_it_is_and_where_that_came_from():
    """A drag coefficient can only be checked against half rho U squared C_d A,
    and A is the hull's own size. The package never carried it."""
    said = json.loads(
        (HERE.parent / "catalog" / "vehicles" / "bluerov2"
         / "dynamics.json").read_text())
    hull = said["hull"]
    assert len(hull["dimensionsM"]) == 3
    assert all(0.05 < one < 2.0 for one in hull["dimensionsM"]), hull
    assert len(hull["dimensionsFrom"]) > 40
    # Read, not measured, and it says which.
    assert "not measured" in hull["dimensionsFrom"]
