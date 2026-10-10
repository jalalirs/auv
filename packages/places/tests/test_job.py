"""A brief from the platform turned into a recipe."""

import pathlib

from iocean_places.job import recipe_of


def test_public_data_becomes_a_calibrated_seabed_with_gebco_under_everything():
    recipe, left = recipe_of({"centre": [22.3, 38.9], "acrossM": 1000, "slug": "reef",
                              "sources": ["sentinel2", "icesat2", "allen-coral-atlas"]}, nasa=True)
    uses = [s["use"] for s in recipe["sources"]]
    assert uses == ["sentinel2-stumpf", "sentinel2-median", "allen-coral-atlas", "icesat2", "gebco"]
    assert [m["use"] for m in recipe["models"]] == ["curve-depth", "colour-depth"]
    assert recipe["scene"]["depth"] == ["colour.depth", "curve.depth", "gebco.depth"]
    assert left == []


def test_without_a_nasa_token_the_laser_is_left_out_and_says_why():
    recipe, left = recipe_of({"centre": [22.3, 38.9], "acrossM": 1000,
                              "sources": ["sentinel2", "icesat2"]}, nasa=False)
    assert "icesat2" not in [s["use"] for s in recipe["sources"]]
    assert recipe["models"] == [] and recipe["scene"]["depth"] == ["stumpf.depth", "gebco.depth"]
    assert left and left[0].startswith("icesat2")


def test_an_organisations_own_survey_comes_first_and_is_feathered_in(tmp_path):
    recipe, _ = recipe_of({"centre": [24.5, -81.4], "acrossM": 800, "sources": ["gebco"],
                           "files": [{"use": "raster", "path": "files/01-dem.tif", "errorM": 0.1},
                                     {"use": "points", "path": "files/02-sound.xyz"},
                                     {"use": "ortho", "path": "files/03-mosaic.tif"}]},
                          inputs=tmp_path, nasa=False)
    assert recipe["sources"][0] == {"use": "raster", "as": "own1", "file": str(tmp_path / "files/01-dem.tif"),
                                    "error": 0.1, "citation": "the organisation's own raster: 01-dem.tif"}
    assert recipe["scene"]["depth"] == ["own1.depth", "own2.depth", "gebco.depth"]
    assert recipe["scene"]["featherCells"] == 10
