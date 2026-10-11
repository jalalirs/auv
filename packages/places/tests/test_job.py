"""A brief from the platform turned into a recipe."""

import pathlib

from iocean_places.job import recipe_of


def test_public_data_becomes_a_calibrated_seabed_with_gebco_under_everything():
    recipe, left, expected = recipe_of({"centre": [22.3, 38.9], "acrossM": 1000, "slug": "reef",
                                        "sources": ["sentinel2", "icesat2", "allen-coral-atlas"]}, nasa=True)
    uses = [s["use"] for s in recipe["sources"]]
    assert uses == ["sentinel2-stumpf", "sentinel2-median", "allen-coral-atlas", "icesat2", "gebco"]
    assert [m["use"] for m in recipe["models"]] == ["curve-depth", "colour-depth"]
    assert expected == ["colour.depth", "curve.depth", "gebco.depth"]
    assert "depth" not in recipe["scene"]                     # every unused depth layer is fused
    assert left == []


def test_without_a_nasa_token_the_laser_is_left_out_and_says_why():
    recipe, left, expected = recipe_of({"centre": [22.3, 38.9], "acrossM": 1000,
                                        "sources": ["sentinel2", "icesat2"]}, nasa=False)
    assert "icesat2" not in [s["use"] for s in recipe["sources"]]
    assert recipe["models"] == [] and expected == ["stumpf.depth", "gebco.depth"]
    assert left and left[0].startswith("icesat2")


def test_an_organisations_own_survey_comes_first_and_is_feathered_in(tmp_path):
    recipe, _, expected = recipe_of({"centre": [24.5, -81.4], "acrossM": 800, "sources": ["gebco"],
                           "files": [{"use": "raster", "path": "files/01-dem.tif", "errorM": 0.1},
                                     {"use": "points", "path": "files/02-sound.xyz"},
                                     {"use": "ortho", "path": "files/03-mosaic.tif"}]},
                          inputs=tmp_path, nasa=False)
    assert recipe["sources"][0] == {"use": "raster", "as": "own1", "file": str(tmp_path / "files/01-dem.tif"),
                                    "error": 0.1, "citation": "the organisation's own raster: 01-dem.tif"}
    assert expected == ["own1.depth", "own2.depth", "gebco.depth"]
    assert recipe["scene"]["featherCells"] == 10


def test_two_layers_of_one_quantity_from_one_source_are_both_kept(monkeypatch):
    import importlib

    import numpy as np
    from iocean_places.grid import Grid
    from iocean_places.layer import Layer, Provenance

    build = importlib.import_module("iocean_places.build")        # the package's `build` is the function
    grid = Grid(24.5, -81.4, 250.0, 8)
    whole = Layer.of(grid, "depth", np.full((8, 8), -5.0), 50.0, Provenance("gebco", "derived", "grid"))
    patchy = Layer.of(grid, "depth", np.full((8, 8), np.nan), 2.0, Provenance("multibeam", "measured", "mosaic"))

    class Two:
        def layers(self, grid, cache=None):
            return [whole, patchy]

    monkeypatch.setattr(build, "source_from", lambda entry: Two())

    class Asked:
        sources = [{"use": "gebco"}]
    Asked.grid = grid
    out = build.products_of(Asked())
    assert out["gebco.depth"] is patchy and out["gebco.depth.1"] is whole


def test_a_reef_is_grown_from_its_regions_mix_and_says_it_was_chosen():
    from iocean_places.job import life_of

    red = life_of(22.3, 38.9, atlas=True)
    assert (red["assemblage"], red["water"]) == ("red-sea", "IB")
    assert "Allen Coral Atlas" in red["coverFrom"] and "not a transect" in red["coverFrom"]
    assert life_of(24.5, -81.4, atlas=False)["assemblage"] == "caribbean"
    assert life_of(21.5, -157.8, atlas=False)["assemblage"] == "hawaii"
    far = life_of(-18.0, 147.0, atlas=False)
    assert far["water"] == "1C" and far["waterFrom"].startswith("assumed")
    assert "not this reef's own" in far["assemblageFrom"]
    assert "inferred" in far["coverFrom"]
