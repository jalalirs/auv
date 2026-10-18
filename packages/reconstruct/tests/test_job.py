"""The parts of the job that are arithmetic."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from iocean_reconstruct.job import OVERLAP, pieces_of  # noqa: E402


def test_the_red_sea_video_is_three_pieces():
    said = pieces_of(756)
    assert [(p["first"], p["last"]) for p in said] == [(1, 252), (253, 504), (505, 756)]
    assert said[0]["trainFirst"] == 1 and said[-1]["trainLast"] == 756
    assert said[1]["trainFirst"] == 253 - OVERLAP and said[1]["trainLast"] == 504 + OVERLAP


def test_every_frame_is_owned_once():
    for n in (20, 131, 259, 400, 1500):
        said = pieces_of(n)
        owned = [i for p in said for i in range(p["first"], p["last"] + 1)]
        assert owned == list(range(1, n + 1))


def test_a_short_swim_is_one_piece():
    assert len(pieces_of(120)) == 1


def test_a_placement_takes_the_strip_centre_to_at(tmp_path):
    import json
    import math

    import numpy as np

    from iocean_reconstruct.lay import placement_of

    grid = np.full((40, 200), np.nan, dtype="<f4")
    grid[10:30, :] = 0.5                                     # a strip 10 m by 1 m, 0.5 m up
    grid.tofile(tmp_path / "surface.f32")
    (tmp_path / "surface.json").write_text(json.dumps({"rows": 40, "columns": 200, "cellM": 0.05,
                                                       "origin": [-5.0, -1.0]}))
    placed = placement_of({"placement": {"at": [100.0, -40.0], "headingDeg": 90.0, "dz": -7.0}}, tmp_path)
    m = np.array(placed["matrix"])
    cx, cy = placed["centre"]
    assert np.allclose((m @ [cx, cy, 0.5, 1.0])[:3], [100.0, -40.0, -6.5], atol=1e-6)
    # Turned a quarter: the strip's x runs north.
    assert np.allclose(m[:3, 0], [0.0, 1.0, 0.0], atol=1e-9) and math.isclose(placed["headingDeg"], 90.0)
    centred = placement_of({"placement": {"centre": True, "depthM": 8}}, tmp_path)
    assert centred["at"] == [0.0, 0.0] and math.isclose(centred["dz"], -8.5)


def test_a_coordinate_is_metres_east_and_north_of_the_centre():
    from iocean_reconstruct.resolve import local_of

    site = {"from": {"centre": {"latitude": 22.284, "longitude": 38.962}}}
    x, y = local_of(site, 22.284 + 0.001, 38.962 + 0.001)
    assert 102 < x < 104 and 110 < y < 111.5
