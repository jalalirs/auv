"""Coral cover from a cover map (what ml/cover writes from a photo mosaic) onto
a place's grid, and into the place."""

import json
import pathlib
import sys

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from iocean_places import Grid  # noqa: E402
from iocean_places.build import build  # noqa: E402
from iocean_places.recipe import Recipe  # noqa: E402
from iocean_places.sources.cover_map import CoverMap  # noqa: E402

GRID = Grid(27.9366, 34.9108, 200.0, 41)               # 5 m cells, at Shushah


def cover_map(folder, checked=True):
    """A 0.5 m map in UTM 36N, 60 m by 40 m around the middle: hard coral 0.3
    and sand 0.7 in its west half, hard coral 0.1 and sand 0.9 in its east,
    its north-west corner imaged only a quarter."""
    from rasterio.transform import from_origin
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", "EPSG:32636", [GRID.longitude], [GRID.latitude])
    e0, n0, cell = xs[0] - 30.0, ys[0] + 20.0, 0.5
    cols, rows = 120, 80
    coral = np.full((rows, cols), 0.1, "float32")
    coral[:, : cols // 2] = 0.3
    seabed = np.ones((rows, cols), "float32")
    seabed[:20, :20] = 0.25
    folder.mkdir(parents=True)
    with rasterio.open(folder / "cover.tif", "w", driver="GTiff", width=cols, height=rows, count=3, dtype="float32",
                       crs="EPSG:32636", transform=from_origin(e0, n0, cell, cell), nodata=float("nan")) as dst:
        dst.write(np.stack([coral, 1 - coral, seabed]))
        for k, name in enumerate(("hard_coral", "sand", "seabed")):
            dst.set_band_description(k + 1, name)
    about = {"model": "test-model", "licence": "Apache-2.0", "tiles": ["a.tif"], "metresPerPixel": 0.01,
             "seabedM2": 2300.0}
    if checked:
        about["checked"] = {"on": "the test sites", "meanAbsError": {"hard_coral": 0.023, "sand": 0.022}}
    (folder / "cover.json").write_text(json.dumps(about))


def test_a_cover_map_onto_the_grid(tmp_path):
    cover_map(tmp_path / "map")
    layers = {one.quantity: one for one in CoverMap(str(tmp_path / "map")).layers(GRID)}
    assert set(layers) == {"cover.hard_coral", "cover.sand"}
    coral, sand = layers["cover.hard_coral"], layers["cover.sand"]
    c = GRID.cells // 2
    assert coral.value[c, c - 3] == pytest.approx(0.3, abs=1e-4)          # 15 m west of the middle
    assert coral.value[c, c + 3] == pytest.approx(0.1, abs=1e-4)
    assert np.allclose((coral.value + sand.value)[coral.covers()], 1.0, atol=1e-4)
    assert np.isnan(coral.value[0, 0]), "outside the map"
    assert np.isnan(coral.value[c + 3, c - 5]), "the corner imaged a quarter is left out"
    assert coral.error[c, c] == pytest.approx(0.023)
    assert coral.provenance[0].kind == "derived"
    assert "the test sites" in coral.provenance[0].citation


def test_imagery_unlike_the_check_needs_its_error_said(tmp_path):
    cover_map(tmp_path / "map", checked=False)
    with pytest.raises(ValueError, match="error"):
        CoverMap(str(tmp_path / "map")).layers(GRID)
    coral = CoverMap(str(tmp_path / "map"), error=0.15).layers(GRID)[0]
    assert np.nanmax(coral.error) == pytest.approx(0.15)
    assert "chosen" in coral.provenance[0].citation


def test_a_place_carries_its_cover(tmp_path):
    cover_map(tmp_path / "map")
    recipe = Recipe.of({"name": "test-reef", "site": {"centre": [GRID.latitude, GRID.longitude], "acrossM": 200,
                                                       "cells": 41},
                        "sources": [{"use": "flat", "depth": 12.0},
                                    {"use": "cover-map", "map": str(tmp_path / "map")}],
                        "scene": {"featherCells": 0}})
    site = build(recipe, tmp_path / "place")
    assert site["cover"]["groups"] == ["hard_coral", "sand"]
    cover = np.fromfile(tmp_path / "place" / "cover.f32", dtype="<f4").reshape(2, 41, 41)
    c = 20
    assert cover[0, c, c - 3] == pytest.approx(0.3, abs=1e-4) and np.isnan(cover[0, 0, 0])
    by = site["cover"]["by"]["hard_coral"]
    assert by["sources"][0]["kind"] == "derived" and by["sources"][0]["errorShare"]["median"] == pytest.approx(0.023)
    heights = json.loads((tmp_path / "place" / "heights.json").read_text())
    assert heights["cover"]["file"] == "cover.f32"
