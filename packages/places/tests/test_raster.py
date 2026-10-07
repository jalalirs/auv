"""A client's survey in its own coordinate system, onto a site's grid, and
over a satellite seabed with no seam where it ends."""

import pathlib
import sys

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from iocean_places import Grid, Layer, Provenance, fuse  # noqa: E402
from iocean_places.models.datum_fit import DatumFit  # noqa: E402
from iocean_places.sources.raster import Raster  # noqa: E402

GRID = Grid(24.54586, -81.4072, 400.0, 201)          # 2 m cells at Looe Key


def survey_tif(path, offset=0.0, depths_positive=False, nodata=-9999.0):
    """A 0.5 m survey in UTM 17N over the middle of the site: a slope of
    -8 m at its west edge falling 1 cm a metre east, plus a datum offset."""
    from rasterio.transform import from_origin
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", "EPSG:32617", [GRID.longitude], [GRID.latitude])
    e0, n0 = xs[0] - 100.0, ys[0] + 60.0                 # 200 m by 120 m, around the middle
    pixel = 0.5
    cols, rows = int(200 / pixel), int(120 / pixel)
    east = e0 + (np.arange(cols) + 0.5) * pixel
    height = np.tile(-8.0 - 0.01 * (east - e0), (rows, 1)) + offset
    height[:4, :4] = nodata                               # a corner the survey did not reach
    values = -height if depths_positive else height
    values[:4, :4] = nodata
    with rasterio.open(path, "w", driver="GTiff", width=cols, height=rows, count=1, dtype="float32",
                       crs="EPSG:32617", transform=from_origin(e0, n0, pixel, pixel), nodata=nodata) as dst:
        dst.write(values.astype("float32"), 1)
    return e0


def test_a_utm_survey_lands_where_it_was_surveyed(tmp_path):
    survey_tif(tmp_path / "survey.tif")
    layer = Raster("survey.tif", path=str(tmp_path), datum="NAVD88").layers(GRID)[0]
    x, y = GRID.xy()
    inside = (np.abs(x) < 95) & (np.abs(y) < 55)
    outside = (np.abs(x) > 110) | (np.abs(y) > 70)
    assert layer.covers()[inside].all() and not layer.covers()[outside].any()
    # The slope, at the right place: -8 m at the survey's west edge (x = -100), 1 cm a metre.
    expected = -8.0 - 0.01 * (x + 100.0)
    assert np.abs(layer.value - expected)[inside].max() < 0.05
    assert "EPSG:32617" in layer.provenance[0].citation and "averaged" in layer.provenance[0].citation
    assert layer.provenance[0].note["surveys"][0]["name"] == "survey.tif"


def test_depths_and_a_datum_are_taken_care_of(tmp_path):
    survey_tif(tmp_path / "survey.tif", offset=0.4, depths_positive=True)
    raw = Raster("survey.tif", path=str(tmp_path), depthsPositive=True).layers(GRID)[0]
    x, y = GRID.xy()
    truth = -8.0 - 0.01 * (x + 100.0)
    # Something measured in the reference datum: a laser track across the survey.
    track = np.where(np.abs(y - 10.0) < 3.0, truth, np.nan)
    measured = Layer.of(GRID, "depth", track, 0.2, Provenance("icesat2", "measured", "a track"))
    layers = {"client": raw, "icesat": measured}
    (fitted,), said = DatumFit("client", "icesat", smallestM2=100.0).run(GRID, layers.__getitem__)
    assert abs(said["datumOffsetM"] - 0.4) < 0.02
    inside = (np.abs(x) < 95) & (np.abs(y) < 55)
    assert np.abs(fitted.value - truth)[inside].max() < 0.06


def test_the_client_replaces_the_satellite_and_the_seam_is_a_slope(tmp_path):
    survey_tif(tmp_path / "survey.tif")
    client = Raster("survey.tif", path=str(tmp_path), error=0.2).layers(GRID)[0]
    x, y = GRID.xy()
    # A satellite seabed a metre too deep everywhere, with its held-out error.
    satellite = Layer.of(GRID, "depth", -9.0 - 0.01 * (x + 100.0), 1.3, Provenance("colour-depth", "derived", "a fit"))
    seabed = fuse([satellite, client], feather=5)
    middle = (np.abs(x) < 60) & (np.abs(y) < 30)
    assert np.allclose(seabed.value[middle], client.value[middle]), "where the client surveyed, the client"
    # Across the survey's east edge, one row: no step bigger than the slope plus the metre spread over the feather.
    row = seabed.value[100, :]
    assert np.abs(np.diff(row)).max() < 0.02 * GRID.cell + 1.0 / 5 + 1e-3
