"""Sources that read what the tools fetched, and the two depth models, on a
made-up reef whose true depth is known."""

import json
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from iocean_places import Grid, Recipe, build  # noqa: E402
from iocean_places.build import products_of, run_models  # noqa: E402
from iocean_places.grid import metres_per_degree  # noqa: E402

GRID = Grid(27.9, 34.9, 400.0, 41)
X, Y = GRID.xy()
TRUE = (-2.0 - 18.0 * (X + 200.0) / 400.0).astype("float32")      # a ramp, 2 m west to 20 m east
ISLAND = (X < -150) & (Y > 150)


def reference(folder: pathlib.Path, seed: int = 3, wobble: float = 0.0) -> pathlib.Path:
    """A reference folder in the formats tools/get-reef, tools/reference,
    tools/coral-atlas and tools/icesat write. `wobble` puts an error in the
    claim that no curve of it can take out and the colour can."""
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True, exist_ok=True)
    centre = {"latitude": GRID.latitude, "longitude": GRID.longitude}
    # get-reef: a claim of the right shape at the wrong scale; the island at +0.6.
    claim = np.where(ISLAND, 0.6, 0.5 * TRUE - 3.0 + wobble * np.sin(Y / 30.0)).astype("<f4")
    claim.tofile(folder / "test.f32")
    (folder / "test.json").write_text(json.dumps({
        "name": "test", "method": "Stumpf", "source": "Copernicus Sentinel-2 TEST", "observedAt": "2026-01-01",
        "opticalLimitM": 22.0, "toCalibrate": "two granules would pin the scale", "centre": centre, "acrossMetres": GRID.across,
        "heightfield": {"rows": GRID.cells, "columns": GRID.cells, "file": "test.f32"}}))
    (folder / "reference.json").write_text(json.dumps({"centre": centre}))
    # tools/reference: the median colour, row 0 north, cut to the square;
    # blue dims with depth, so its log is linear in it.
    blue = 200.0 * np.exp(np.where(ISLAND, 0.0, TRUE) / 26.0)
    rgb = np.stack([np.full_like(blue, 40.0), 0.8 * blue, blue], -1)[::-1].astype("float32")
    np.save(folder / "sentinel_median_rgb.npy", rgb)
    (folder / "sentinel.json").write_text(json.dumps({"bbox": list(GRID.bounds()),
                                                      "scenes": [{"date": "2026-01-01", "id": "S2"}]}))
    # tools/coral-atlas: reef slope over the west half.
    east, north = metres_per_degree(GRID.latitude)
    lon = lambda x: GRID.longitude + x / east  # noqa: E731
    lat = lambda y: GRID.latitude + y / north  # noqa: E731
    ring = [[lon(-210), lat(-210)], [lon(0), lat(-210)], [lon(0), lat(210)], [lon(-210), lat(210)], [lon(-210), lat(-210)]]
    slope = {"type": "Feature", "properties": {"class_name": "Reef Slope"},
             "geometry": {"type": "Polygon", "coordinates": [ring]}}
    (folder / "coral-atlas-geomorphic.geojson").write_text(json.dumps({"features": [slope]}))
    # tools/icesat: two tracks of photons, metres from the centre.
    tx = np.concatenate([np.linspace(-190, 190, 400), np.full(400, 60.0)])
    ty = np.concatenate([np.full(400, -40.0), np.linspace(-190, 190, 400)])
    tz = (-2.0 - 18.0 * (tx + 200.0) / 400.0) + rng.normal(0, 0.15, len(tx))
    np.save(folder / "icesat_depths.npy", np.column_stack([tx, ty, tz, np.full(len(tx), 0.17)]).astype("float32"))
    (folder / "icesat.json").write_text(json.dumps({"source": "ICESat-2 ATL24 TEST", "photons": len(tx)}))
    return folder


RECIPE = {
    "name": "test-reef", "site": {"centre": [27.9, 34.9], "acrossM": 400, "cells": 41},
    "sources": [{"use": "sentinel2-stumpf", "as": "stumpf", "place": "test"},
                {"use": "sentinel2-median", "as": "sentinel"},
                {"use": "allen-coral-atlas", "as": "atlas"},
                {"use": "icesat2", "as": "icesat"}],
    "models": [{"use": "curve-depth", "as": "curve", "depth": "stumpf.depth", "truth": "icesat.depth.points",
                "land": "stumpf.land", "reef": "atlas.geomorphic"},
               {"use": "colour-depth", "as": "colour", "depth": "stumpf.depth", "red": "sentinel.red",
                "green": "sentinel.green", "blue": "sentinel.blue", "classes": "atlas.geomorphic",
                "truth": "icesat.depth.points", "land": "stumpf.land"}],
    "scene": {"depth": ["colour.depth", "curve.depth"], "featherCells": 0},
}


def test_the_sources_read_what_the_tools_wrote(tmp_path):
    products = products_of(Recipe.of(RECIPE), reference(tmp_path / "ref"))
    assert np.allclose(products["stumpf.land"].value, ISLAND)
    assert products["atlas.geomorphic"].classes == ("Reef Slope",)
    assert products["atlas.geomorphic"].covers()[X < -10].all() and not products["atlas.geomorphic"].covers()[X > 10].any()
    # Row 0 of the picture is north; row 0 of the grid is south.
    assert products["sentinel.blue"].value[0, 0] < products["sentinel.blue"].value[0, -1] * 3
    assert np.isclose(products["sentinel.blue"].value[-1, 0], 200.0)       # the island, north-west
    assert len(products["icesat.depth.points"].value) == 800


def test_the_curve_rescales_the_claim_and_keeps_the_island(tmp_path):
    recipe = Recipe.of({**RECIPE, "models": RECIPE["models"][:1]})
    products = products_of(recipe, reference(tmp_path / "ref"))
    said, used = run_models(recipe, products)
    curve = products["curve.depth"]
    assert abs(said["curve"]["coefficients"][0] - 2.0) < 0.05 and abs(said["curve"]["coefficients"][1] - 6.0) < 0.3
    assert np.abs(curve.value - TRUE)[~ISLAND].max() < 0.3
    assert said["curve"]["rmsHeldOutM"] < 0.3 and said["curve"]["shape"] == "straight line"
    # The island is in the reef map's west half, so it is reef the infrared took for land: awash.
    assert np.allclose(curve.value[ISLAND], -0.3)
    assert "stumpf.depth" in used and "icesat.depth.points" in used


def test_a_place_from_the_reference_folder(tmp_path):
    site = build(Recipe.of(RECIPE), tmp_path / "place", reference(tmp_path / "ref", wobble=1.5))
    height = np.fromfile(tmp_path / "place" / "seabed.f32", dtype="<f4").reshape(41, 41)
    water = ~ISLAND
    assert np.abs(height - TRUE)[water].max() < 0.3
    note = json.loads((tmp_path / "place" / "heights.json").read_text())
    assert note["file"] == "seabed.f32" and note["surveyed"] is False
    assert note["fittedAgainst"]["rmsHeldOutM"] < 0.3, "the model that made most of the seabed says how it was fitted"
    assert set(site["from"]["models"]) == {"curve", "colour"}
    kinds = {s["source"]: s["kind"] for s in site["from"]["depth"]["sources"]}
    assert kinds.get("colour-depth") == "derived"
    models = site["from"]["models"]
    assert models["colour"]["rmsHeldOutM"] < models["curve"]["rmsHeldOutM"], "the colour knows what the claim got wrong"
    assert site["beginAt"][2] < 0, "a dive begins under water"
    # What the satellite's own note said, carried, or make-site deletes it from the place.
    assert note["source"] == "Copernicus Sentinel-2 TEST" and note["method"] == "Stumpf"
    assert note["observedAt"] == "2026-01-01" and note["opticalLimitM"] == 22.0
    assert "toCalibrate" not in note and site["from"]["models"]["colour"]["wasOwed"]


def test_a_model_asked_for_something_nobody_made(tmp_path):
    recipe = Recipe.of({**RECIPE, "models": [{**RECIPE["models"][0], "truth": "lidar.depth.points"}]})
    with pytest.raises(ValueError, match="nothing called 'lidar.depth.points'"):
        build(recipe, tmp_path / "place", reference(tmp_path / "ref"))


def test_a_fit_does_not_make_dry_land_of_water(tmp_path):
    """A line whose offset lifts the shallowest claims above the surface
    (Al Fahal's did): with keepWet those cells stay awash; without it the
    place is rebuilt as it was."""
    folder = reference(tmp_path / "ref")
    claim = np.fromfile(folder / "test.f32", dtype="<f4").reshape(41, 41)
    # A claim stretched and offset as Al Fahal's was (measured = 0.4 claim + 2.8),
    # and a patch away from the tracks the satellite read as barely under water.
    stretched = 2.5 * TRUE - 7.0
    patch = (X > 150) & (Y < -150)
    np.where(ISLAND, 0.6, np.where(patch, -1.0, stretched)).astype("<f4").tofile(folder / "test.f32")
    for keep, top in ((True, -0.3), (False, None)):
        model = {**RECIPE["models"][0], "keepWet": keep}
        model.pop("reef")
        recipe = Recipe.of({**RECIPE, "models": [model]})
        products = products_of(recipe, folder)
        said, _ = run_models(recipe, products)
        water = products["curve.depth"].value[~ISLAND]
        if top is None:
            assert said["curve"]["driedCells"] > 0 and water.max() > 0
        else:
            assert said["curve"]["keptWetCells"] > 0 and water.max() <= top
    claim.tofile(folder / "test.f32")
