"""Turning a place into what a marine department asks for.

A score and a video is not a deliverable, and a deliverable that does not say
which of its numbers anybody measured is worse than none: it gets cited back
as though the model had measured them.
"""

import csv
import importlib.machinery
import importlib.util
import json
import math
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename=None):
    loader = importlib.machinery.SourceFileLoader(
        name, str(HERE / (filename or name)))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _deliver():
    return _load("deliver")


def _make_site():
    return _load("make_site", "make-site")


def test_the_georeference_is_the_inverse_of_how_the_place_was_built():
    """`tools/deliver` carries its own copy of `metres_per_degree` on purpose:
    a transform whose forward and backward halves share an implementation
    cannot be checked by comparing them. This is that check."""
    deliver, make_site = _deliver(), _make_site()
    for latitude in (-40.0, 0.0, 21.45, 24.54586, 24.5, 60.0):
        assert deliver.metres_per_degree(latitude) == pytest.approx(
            make_site.metres_per_degree(latitude), rel=1e-12)


def test_a_colony_comes_back_where_it_was_put():
    """Round-trip a site-local position out to the Earth and back through the
    forward transform the place was sampled with."""
    deliver, make_site = _deliver(), _make_site()
    centre = {"latitude": 24.54586, "longitude": -81.4072}
    east, north = make_site.metres_per_degree(centre["latitude"])
    for x, y in ((0.0, 0.0), (-160.4, -14.33), (480.0, -499.0), (12.5, 333.0)):
        latitude, longitude = deliver.where_on_earth(centre, x, y)
        back_x = (longitude - centre["longitude"]) * east
        back_y = (latitude - centre["latitude"]) * north
        assert back_x == pytest.approx(x, abs=1e-6)
        assert back_y == pytest.approx(y, abs=1e-6)


def test_north_and_east_are_not_swapped():
    """The one error in a georeference that puts a reef in the wrong country
    and produces no warning of any kind."""
    deliver = _deliver()
    centre = {"latitude": 24.0, "longitude": -81.0}
    north = deliver.where_on_earth(centre, 0.0, 1000.0)
    east = deliver.where_on_earth(centre, 1000.0, 0.0)
    assert north[0] > centre["latitude"] and north[1] == pytest.approx(centre["longitude"])
    assert east[1] > centre["longitude"] and east[0] == pytest.approx(centre["latitude"])


def test_a_degree_of_longitude_is_shorter_further_north():
    deliver = _deliver()
    assert (deliver.metres_per_degree(60.0)[0]
            < deliver.metres_per_degree(24.0)[0]
            < deliver.metres_per_degree(0.0)[0])


def test_cover_saturates_rather_than_exceeding_one():
    """Colonies are scattered, not tiled, so they land on each other. A cell
    whose colonies add to more than its area is fully covered, not a hundred
    and forty per cent — the same arithmetic tools/reef.py applies to a whole
    site, per cell."""
    deliver = _deliver()
    across, cell = 100.0, deliver.COVER_CELL_M
    # Forty square metres of colony, all in one five-metre cell.
    colonies = {"at": [(0.1, 0.1, -3.0)] * 40}
    grid = deliver.cover_raster(colonies, {"m2": [1.0] * 40}, across, cell)
    assert grid.max() < 1.0
    assert grid.max() > 0.7
    assert (grid >= 0).all() and (grid <= 1).all()


def test_a_surveyed_size_is_the_measurement_and_a_grown_one_is_not():
    """On a surveyed reef the instancer's scale *is* the diameter the survey
    recorded, halved. On a grown reef it is a draw against a prototype. The
    inventory must not present the second as though it were the first."""
    deliver = _deliver()
    colonies = {"which": [0, 1], "scale": [(0.25, 0.25, 0.25), (0.5, 0.5, 0.5)]}

    surveyed = deliver.sizes_of(colonies, None, surveyed=True)
    assert surveyed["acrossM"] == pytest.approx([0.5, 1.0])
    assert surveyed["m2"] == pytest.approx(
        [math.pi * 0.0625, math.pi * 0.25])

    grown = deliver.sizes_of(colonies, [2.0, 2.0], surveyed=False)
    assert grown["m2"] == pytest.approx([2.0 * 0.0625, 2.0 * 0.25])


def test_it_refuses_a_place_that_does_not_say_what_its_prototypes_are():
    """Its first version worked the growth forms out of the USD, assuming the
    prototype index was kind times variants plus variant and reading the names
    off `reef.kinds` — which on a surveyed place is a histogram of what the
    survey counted. Every row of a published CSV came out "low" or "unknown"
    and every footprint was a hundred times too small, and it looked like a
    reef with no cover on it rather than like an error."""
    deliver = _deliver()
    with pytest.raises(SystemExit):
        deliver.prototypes_in({"name": "somewhere", "reef": {"kinds": {"low": 5}}})


def test_a_place_with_no_centre_cannot_be_delivered(tmp_path):
    """A deliverable without a georeference is a picture."""
    deliver = _deliver()
    place = tmp_path / "nowhere"
    place.mkdir()
    (place / "site.json").write_text(json.dumps({"name": "nowhere", "from": {}}))
    with pytest.raises(SystemExit):
        deliver.deliver(place, tmp_path / "out")


def test_the_grid_is_written_north_first(tmp_path):
    """Row 0 of the array is the south edge and an ASCII grid is written from
    the north down. This is the same flip every texture here needs and it is
    the one that puts a reef a mile from where the survey put it."""
    deliver = _deliver()
    grid = np.zeros((4, 4))
    grid[0, 0] = 1.0          # south-west corner
    deliver.write_grid(tmp_path, grid, {"latitude": 24.0, "longitude": -81.0},
                       20.0, 5.0)
    lines = (tmp_path / "cover.asc").read_text().splitlines()
    assert lines[0].split()[1] == "4" and lines[1].split()[1] == "4"
    assert float(lines[2].split()[1]) == pytest.approx(-10.0)
    # Six header lines, then north to south: the 1.0 is on the last row.
    assert float(lines[-1].split()[0]) == pytest.approx(1.0)
    assert float(lines[6].split()[0]) == pytest.approx(0.0)
    assert "Azimuthal_Equidistant" in (tmp_path / "cover.prj").read_text()


def test_provenance_marks_the_growth_form_unmeasured_even_on_a_survey():
    """A detector that found a colony in an orthomosaic found a blob of a size
    and a colour. Which growth form it is was assigned afterwards, and on a
    surveyed reef it is the one column that is not an observation while
    everything beside it is."""
    deliver = _deliver()
    said = deliver.provenance({
        "name": "looe-key",
        "from": {"surveyed": True, "centre": {"latitude": 24.5, "longitude": -81.4}},
        "reef": {"sizesAre": "surveyed", "cover": {"measured": True}},
    })
    assert said["columns"]["growthForm"]["measured"] is False
    assert said["columns"]["latitude"]["measured"] is True
    assert said["columns"]["acrossM"]["measured"] is True


def test_provenance_marks_a_grown_reef_as_grown():
    deliver = _deliver()
    said = deliver.provenance({
        "name": "red-sea",
        "from": {"surveyed": False, "centre": {"latitude": 22.0, "longitude": 38.0}},
        "reef": {"sizesAre": "grown", "cover": {"measured": False}},
    })
    for column in ("latitude", "longitude", "acrossM", "footprintM2",
                   "growthForm"):
        assert said["columns"][column]["measured"] is False, column
    said_first = said["readThisFirst"]
    assert "are not real colonies" in said_first
    assert "observation of a living animal" in said_first
