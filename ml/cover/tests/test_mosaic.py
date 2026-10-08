"""A cover map from two small synthetic mosaic tiles, with the stand-in
network: the cells' shares must be what was painted."""

import json

import numpy as np
import pytest

pytest.importorskip("torch")
rasterio = pytest.importorskip("rasterio")

from iocean_cover.classes import Groups  # noqa: E402
from iocean_cover.mosaic import make  # noqa: E402

from test_segment import fake_segmenter  # noqa: E402


def _tile(path, left, top, rgba, res=0.01):
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", width=rgba.shape[2], height=rgba.shape[1], count=4, dtype="uint8",
                       crs="EPSG:6346", transform=from_origin(left, top, res, res)) as dst:
        dst.write(rgba)


def test_cells_count_what_was_painted(tmp_path):
    a = np.zeros((4, 200, 200), np.uint8)
    a[3] = 255                                  # all imaged
    a[0, :, :100] = 255                         # west half bright: class 1, coral
    b = np.zeros((4, 200, 200), np.uint8)
    b[3, :100] = 255                            # north half imaged, sand
    _tile(tmp_path / "a.tif", 1000.0, 2000.0, a)
    _tile(tmp_path / "b.tif", 1002.0, 2000.0, b)
    seg = fake_segmenter()
    groups = Groups(seg.id2label, {"hard_coral": ["porites alive"], "sand": ["sand"], "not_seabed": ["unlabeled"]})
    said = make(seg, groups, [tmp_path / "a.tif", tmp_path / "b.tif"], tmp_path / "out",
                {"metres_per_pixel": 0.01, "cell_m": 0.5, "block": 150, "margin": 20}, {"model": "fake"})
    with rasterio.open(tmp_path / "out" / "cover.tif") as src:
        coral, sand, seabed = src.read(1), src.read(2), src.read(3)
        assert src.shape == (4, 8)
    assert np.allclose(coral[:, :2], 1, atol=0.01) and np.allclose(sand[:, 2:4], 1, atol=0.01)
    assert np.allclose(seabed[:, :4], 1)
    assert np.allclose(seabed[:2, 4:], 1) and np.allclose(seabed[2:, 4:], 0)
    assert np.isnan(coral[2:, 4:]).all()
    assert said["shares"]["hard_coral"] == pytest.approx(2 / 6, abs=0.02)    # 2 m2 of 6 m2 of seabed
    assert json.loads((tmp_path / "out" / "cover.json").read_text())["cells"] == [4, 8]
