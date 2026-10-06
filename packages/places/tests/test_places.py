"""The places module: layers on one grid, fusion by error, a place from a recipe."""

import json
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from iocean_places import Grid, Layer, Provenance, Recipe, build, fuse  # noqa: E402
from iocean_places.sources import Points  # noqa: E402

GRID = Grid(27.9, 34.9, 200.0, 41)
SURVEY = Provenance("survey", "measured", "a multibeam survey")
SATELLITE = Provenance("satellite", "derived", "satellite-derived depth")


def half(value, east: bool):
    out = np.full((GRID.cells, GRID.cells), np.nan, dtype="float32")
    x, _ = GRID.xy()
    out[(x > 0) if east else np.ones_like(x, bool)] = value
    return out


def test_fusion_takes_the_better_source_and_says_whose():
    survey = Layer.of(GRID, "depth", half(-10.0, east=True), 0.2, SURVEY)
    satellite = Layer.of(GRID, "depth", half(-12.0, east=False), 1.5, SATELLITE)
    fused = fuse([satellite, survey], feather=0)
    x, _ = GRID.xy()
    assert np.allclose(fused.value[x > 0], -10.0) and np.allclose(fused.value[x <= 0], -12.0)
    assert fused.provenance[fused.source[0, -1]].source == "survey"
    assert fused.provenance[fused.source[0, 0]].source == "satellite"
    said = fused.said()
    assert {s["source"] for s in said["sources"]} == {"survey", "satellite"}
    assert abs(sum(s["share"] for s in said["sources"]) - 1.0) < 1e-6


def test_the_seam_is_blended_not_stepped():
    survey = Layer.of(GRID, "depth", half(-10.0, east=True), 0.2, SURVEY)
    satellite = Layer.of(GRID, "depth", half(-12.0, east=False), 1.5, SATELLITE)
    fused = fuse([satellite, survey], feather=4)
    row, err = fused.value[20], fused.error[20]
    assert np.abs(np.diff(row)).max() <= 0.5 + 1e-6, "a 2 m step at the seam is spread over the feather"
    between = (row > -12.0) & (row < -10.0)
    assert between.sum() == 3, "three cells of slope where the survey tapers off"
    assert np.all((err[between] > 0.2) & (err[between] < 1.5))
    # Inside its coverage the survey is believed outright, not averaged with a worse guess.
    assert row[-1] == -10.0 and err[-1] == np.float32(0.2)


def test_points_say_how_far_they_are_from_a_sounding(tmp_path):
    rows = np.array([[0.0, 0.0, -8.0], [50.0, 50.0, -9.0]])
    np.savetxt(tmp_path / "s.xyz", rows)
    layer = Points(str(tmp_path / "s.xyz"), error=0.1, reach=40.0, slope=0.1).layers(GRID)[0]
    centre = GRID.cells // 2
    assert abs(layer.value[centre, centre] + 8.0) < 1e-6
    assert layer.error[centre, centre] < 0.2
    assert np.isnan(layer.value[0, 0]), "nothing within reach of the corner"


def test_a_place_from_a_recipe(tmp_path):
    np.savetxt(tmp_path / "s.xyz", np.array([[0.0, 0.0, -8.0]]))
    recipe = Recipe.of({"name": "test-reef", "site": {"centre": [27.9, 34.9], "acrossM": 200, "cells": 41},
                        "sources": [{"use": "flat", "depth": 12.0},
                                    {"use": "points", "path": str(tmp_path / "s.xyz"), "reach": 30.0}],
                        "scene": {"featherCells": 0}})
    site = build(recipe, tmp_path / "place")
    place = tmp_path / "place"
    for name in ("seabed.f32", "seabed.usda", "error.f32", "sources.u8", "site.json", "recipe.json"):
        assert (place / name).exists(), name
    height = np.fromfile(place / "seabed.f32", dtype="<f4").reshape(41, 41)
    assert abs(height[20, 20] + 8.0) < 1e-6 and abs(height[0, 0] + 12.0) < 1e-6
    kinds = {s["source"]: s["kind"] for s in site["from"]["depth"]["sources"]}
    assert kinds == {"flat": "assumed", "points": "measured"}
    assert Recipe.read(place / "recipe.json").said() == recipe.said()


def test_a_square_nobody_covers_is_refused(tmp_path):
    np.savetxt(tmp_path / "s.xyz", np.array([[0.0, 0.0, -8.0]]))
    recipe = Recipe.of({"name": "gap", "site": {"centre": [27.9, 34.9], "acrossM": 200, "cells": 41},
                        "sources": [{"use": "points", "path": str(tmp_path / "s.xyz"), "reach": 10.0}]})
    with pytest.raises(ValueError, match="no depth from any source"):
        build(recipe, tmp_path / "gap")


def test_numbers_have_a_kind():
    with pytest.raises(ValueError):
        Provenance("x", "guessed", "")
