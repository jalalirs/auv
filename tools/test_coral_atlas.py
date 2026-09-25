"""The Allen Coral Atlas: a measurement of what the ground is.

Every reef here but Looe Key had its habitat *inferred* from the slope and
relief of its own bathymetry, and that inference is the weakest thing under a
reef: it decides how much of a site is reef at all, which is the denominator
of every cover figure the place reports.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _atlas():
    loader = importlib.machinery.SourceFileLoader(
        "coral_atlas", str(HERE / "coral-atlas"))
    spec = importlib.util.spec_from_loader("coral_atlas", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _make_site():
    loader = importlib.machinery.SourceFileLoader(
        "make_site", str(HERE / "make-site"))
    spec = importlib.util.spec_from_loader("make_site", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_its_classes_are_the_ones_the_pipeline_already_reads():
    """A place mapped by the Atlas and a place mapped by Florida's reef tract
    survey have to be read by the same code, or there are two habitat
    pipelines and only one of them gets fixed."""
    atlas, make_site = _atlas(), _make_site()
    for name, code in atlas.AS_HABITAT.items():
        assert code in make_site.HARDNESS, (name, code)
        assert code in make_site.HABITAT_NAMES, (name, code)
    assert atlas.UNMAPPED == 0
    assert make_site.HABITAT_NAMES[0] == "unmapped"


def test_the_georeference_is_the_one_every_other_tool_uses():
    atlas, make_site = _atlas(), _make_site()
    for latitude in (-20.0, 0.0, 21.45, 22.284, 24.54586):
        assert atlas.metres_per_degree(latitude) == pytest.approx(
            make_site.metres_per_degree(latitude), rel=1e-12)


def test_a_polygon_lands_where_its_coordinates_say():
    atlas = _atlas()
    centre, across, texels = (22.284, 38.962), 1000.0, 64
    east, north = atlas.metres_per_degree(centre[0])
    # A square 100 m east and 100 m north of the centre.
    def at(x, y):
        return [centre[1] + x / east, centre[0] + y / north]
    feature = {"properties": {"class_name": "Coral/Algae"},
               "geometry": {"type": "Polygon", "coordinates": [[
                   at(50, 50), at(150, 50), at(150, 150), at(50, 150),
                   at(50, 50)]]}}
    grid = np.array(atlas.paint([feature], centre, across, texels), dtype="int16")
    assert (grid == atlas.AS_HABITAT["Coral/Algae"]).any()
    rows, columns = np.nonzero(grid == atlas.AS_HABITAT["Coral/Algae"])
    # East is +column, north is +row: row 0 is the south edge, which is what
    # every heightfield and every texture on this platform uses.
    assert columns.mean() > texels / 2
    assert rows.mean() > texels / 2


def test_coral_is_drawn_last_so_sand_does_not_bury_it():
    """Sand is the background of a reef and coral is the exception."""
    atlas = _atlas()
    assert atlas.IN_ORDER[0] == "Sand"
    assert atlas.IN_ORDER[-1] == "Coral/Algae"
    assert set(atlas.IN_ORDER) == set(atlas.AS_HABITAT)


def test_coral_and_algae_being_one_class_is_said_out_loud():
    """Sentinel-2 cannot separate living coral from the algae on and beside
    it, so that number is an upper bound on coral cover and not a measurement
    of it."""
    source = (HERE / "coral-atlas").read_text()
    assert "upper bound on coral cover" in source
    assert "readThisFirst" in source


def test_a_page_is_not_an_answer():
    """A WFS will silently give you a page rather than the answer, and a
    habitat map missing its eastern half looks exactly like a reef that
    stops."""
    source = (HERE / "coral-atlas").read_text()
    assert "numberMatched" in source
    assert "this is a" in source and "page, not the answer" in source


def test_unmapped_ground_falls_back_to_the_inference():
    """Class 0 is "unmapped" and HARDNESS gives it 0.5, which is honest for
    one polygon and is the can't-be-wrong default over a large area: it says
    the same thing about every square metre of it. The Atlas maps Al Fahal's
    flat and lagoon and not its fore-reef slope, so a quarter of that site was
    taking a flat half and dominating the habitat figure."""
    source = (HERE / "make-site").read_text()
    assert "nobody_looked = kinds == 0" in source
    assert "np.where(nobody_looked, guessed, hard)" in source


def test_derived_colour_takes_hardness_at_any_size():
    """It assumed 1024 and held for a year because the only caller handed in
    `derived_hardness(..., n=1024)`. Habitat polygons come in at 4096, and the
    one place that had those also had an orthomosaic — so it took the
    photographed branch and never reached here. Al Fahal is the first place
    with a habitat map and no photograph of itself."""
    make_site = _make_site()
    height = np.full((256, 256), -8.0)
    for n in (256, 1024, 4096):
        out = make_site.derived_colour(height, np.full((n, n), 0.5, dtype="float32"),
                                       1000.0, n=512)
        assert out.shape == (512, 512, 3), n


def test_the_shares_reported_are_of_the_site_and_not_of_the_polygons():
    """A WFS bbox query returns every polygon that *intersects* the box,
    whole, and `area_sqkm` is the whole polygon's area. Over a
    one-kilometre site with reef polygons a kilometre across, Kāne'ohe's
    areas added up to 2.24 km² "of 1.00" — which is not a share of anything
    and was being printed as one."""
    source = (HERE / "coral-atlas").read_text()
    assert "onSiteShare" in source
    assert "unmappedShare" in source
    # And the shares come off the raster, which is clipped to the site.
    assert 'float((named == i + 1).mean())' in source


def test_a_geomorphic_class_is_not_painted_as_a_habitat_code():
    """Reef crest, back reef slope and lagoon are a different taxonomy from
    sand, rubble and coral. Painting one into the other's codes would write a
    habitat map that says "aggregate reef" where the Atlas said "plateau"."""
    atlas = _atlas()
    centre, across, texels = (21.49, -157.83), 1000.0, 32
    east, north = atlas.metres_per_degree(centre[0])

    def at(x, y):
        return [centre[1] + x / east, centre[0] + y / north]

    feature = {"properties": {"class_name": "Plateau"},
               "geometry": {"type": "Polygon", "coordinates": [[
                   at(-100, -100), at(100, -100), at(100, 100),
                   at(-100, 100), at(-100, -100)]]}}
    # With the benthic map it paints nothing, because "Plateau" is not one.
    benthic = np.array(atlas.paint([feature], centre, across, texels),
                       dtype="int16")
    assert (benthic == atlas.UNMAPPED).all()
    # With its own it paints.
    own = np.array(atlas.paint([feature], centre, across, texels,
                               codes={"Plateau": 1}, order=["Plateau"]),
                   dtype="int16")
    assert (own == 1).any()


def test_two_atlas_classes_sharing_a_habitat_code_are_still_counted_apart():
    """Sand and Microalgal Mats are both sediment here, because a film of
    algae on mud is mud. Counting names against the habitat grid gave both of
    them the same pixels: Al Fahal reported Sand at 22.9% of the site and
    Microalgal Mats at 22.9%, which are the same 22.9%."""
    atlas = _atlas()
    assert atlas.AS_HABITAT["Sand"] == atlas.AS_HABITAT["Microalgal Mats"]
    source = (HERE / "coral-atlas").read_text()
    assert "Painted twice, on purpose" in source
    assert "which are\n        # the same 22.9%." in source
