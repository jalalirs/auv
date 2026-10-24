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


def test_two_assets_whose_ground_touches_are_said_to_overlap():
    import numpy as np

    from iocean_reconstruct.lay import overlaps

    strip = np.stack(np.meshgrid(np.arange(0, 20.0), np.arange(0, 3.0)), -1).reshape(-1, 2)
    apart = [{"name": "a", "ground": strip}, {"name": "b", "ground": strip + [100.0, 0.0]}]
    touching = [{"name": "a", "ground": strip}, {"name": "b", "ground": strip + [19.5, 0.0]}]
    assert overlaps(apart) == []
    said = overlaps(touching)
    assert len(said) == 1 and "a and b overlap" in said[0]


def test_the_edge_fade_is_fifteen_percent_of_the_narrow_width_from_1_to_4_m():
    from iocean_reconstruct.job import edge_for

    assert edge_for(10.0) == 1.5                             # a diver's reef: close to the metre it was
    assert edge_for(2.0) == 1.0 and edge_for(0.0) == 1.0
    assert edge_for(60.0) == 4.0
    assert abs(edge_for(20.0) - 3.0) < 1e-9


def test_a_strips_narrow_width_is_across_it_not_along_it(tmp_path):
    import json

    import numpy as np

    from iocean_reconstruct.job import edge_of, narrow_width

    known = np.zeros((48, 660), dtype=bool)
    known[4:44, 10:650] = True                               # 160 m by 10 m in 25 cm cells
    known[20:24, 300:304] = False                            # a hole is not an edge
    assert abs(narrow_width(known, 0.25) - 10.0) < 0.6
    grid = np.full((220, 420), np.nan, dtype="<f4")
    grid[10:210, 10:410] = -0.2                              # a diver's reef 20 m by 10 in 5 cm cells
    grid.tofile(tmp_path / "surface.f32")
    (tmp_path / "surface.json").write_text(json.dumps({"rows": 220, "columns": 420, "cellM": 0.05,
                                                       "origin": [0.0, 0.0]}))
    assert abs(edge_of(tmp_path) - 1.5) < 0.05


def _strip_into_a_place(tmp_path, grey=0.5):
    """A place 100 m across with a map 200 texels a side in one grey, and a
    strip 20 m by 4 in 25 cm cells laid in its middle."""
    import json

    import numpy as np
    from PIL import Image

    place, rec = tmp_path / "place", tmp_path / "rec"
    (place / "textures").mkdir(parents=True)
    rec.mkdir()
    Image.fromarray(np.full((200, 200, 3), round(grey * 255), dtype="uint8")).save(
        place / "textures" / "site_colour.jpg", quality=95)
    (place / "site.json").write_text(json.dumps({"from": {"acrossMetres": 100.0}, "ground": {"soft": "sand"},
                                                 "reconstructions": [{"name": "strip"}]}))
    grid = np.full((16, 80), -0.1, dtype="<f4")
    grid.tofile(rec / "surface.f32")
    (rec / "surface.json").write_text(json.dumps({"rows": 16, "columns": 80, "cellM": 0.25, "origin": [0.0, 0.0]}))
    P = np.eye(4)
    P[:3, 3] = [-10.0, -2.0, -17.0]                          # its middle on the place's
    return place, rec, P


def _texel(x, y, across=100.0, n=200):
    return int(round((0.5 - y / across) * n - 0.5)), int(round((x / across + 0.5) * n - 0.5))


def test_the_ground_takes_the_strips_colour_under_it_and_keeps_its_own_far_off():
    import numpy as np

    from iocean_reconstruct.lay import ground_blend

    rgb = np.full((200, 200, 3), 0.5)
    whole = np.ones((16, 80), dtype=bool)
    P = np.eye(4)
    P[:2, 3] = [-10.0, -2.0]
    out, how = ground_blend(rgb, 100.0, P, whole, 0.25, (0.0, 0.0), (0.8, 0.6, 0.4), falloff=15.0)
    colour = np.array([0.8, 0.6, 0.4])
    assert np.allclose(out[_texel(0.0, 0.0)], colour) and np.allclose(out[_texel(9.5, 1.5)], colour)
    assert np.allclose(out[_texel(0.0, 20.0)], 0.5) and np.allclose(out[_texel(30.0, 0.0)], 0.5)
    assert np.allclose(out[0, 0], 0.5) and how["texelsUnder"] > 0 and np.allclose(how["before"], 0.5)
    # North of the strip, from its edge (2 m) out past the falloff: red falls
    # from the strip's to the place's, never back, in small steps.
    red = np.array([out[_texel(0.0, y)][0] for y in np.arange(2.5, 20.0, 0.5)])
    assert np.all(np.diff(red) <= 1e-12) and np.abs(np.diff(red)).max() < 0.03
    halfway = out[_texel(0.0, 2.0 + 7.5)][0]
    assert 0.6 < halfway < 0.7                               # smoothstep's middle, about


def test_a_strip_turned_is_coloured_where_it_lies():
    import numpy as np

    from iocean_reconstruct.lay import ground_blend

    rgb = np.full((200, 200, 3), 0.5)
    whole = np.ones((16, 80), dtype=bool)                    # 20 m along x, 4 m across
    P = np.eye(4)
    P[:2, :2] = [[0.0, -1.0], [1.0, 0.0]]                    # turned a quarter: it runs north
    P[:2, 3] = [2.0, -10.0]
    out, _ = ground_blend(rgb, 100.0, P, whole, 0.25, (0.0, 0.0), (1.0, 1.0, 1.0), falloff=5.0)
    assert np.allclose(out[_texel(0.0, 9.0)], 1.0)           # along it, north of the middle
    assert np.allclose(out[_texel(9.0, 0.0)], 0.5)           # where it would be unturned: off it, past the falloff


def test_laying_a_strip_writes_the_blend_and_says_where_its_colour_came_from(tmp_path):
    import json

    import numpy as np
    from PIL import Image

    from iocean_reconstruct.lay import GROUND_FALLOFF_M, blend_ground

    place, rec, P = _strip_into_a_place(tmp_path)
    said = blend_ground(place, "strip", rec, P, [], colour=(0.8, 0.6, 0.4))
    rgb = np.asarray(Image.open(place / "textures" / "site_colour.jpg").convert("RGB"), dtype=float) / 255.0
    assert np.abs(rgb[_texel(0.0, 0.0)] - [0.8, 0.6, 0.4]).max() < 0.03
    assert np.abs(rgb[_texel(0.0, 30.0)] - 0.5).max() < 0.03
    site = json.loads((place / "site.json").read_text())
    told = site["reconstructions"][0]["groundColour"]
    assert told == said and told["falloffM"] == GROUND_FALLOFF_M and told["from"].startswith("derived: from the asset")
    assert told["colour"] == [0.8, 0.6, 0.4] and np.allclose(told["placeColourBefore"], 0.5, atol=0.01)


def test_a_place_with_no_colour_map_is_left_alone(tmp_path):
    import json

    from iocean_reconstruct.lay import blend_ground

    place, rec, P = _strip_into_a_place(tmp_path)
    (place / "textures" / "site_colour.jpg").unlink()
    before = (place / "site.json").read_text()
    assert blend_ground(place, "strip", rec, P, [], colour=(0.8, 0.6, 0.4)) is None
    assert (place / "site.json").read_text() == before and "groundColour" not in json.loads(before)["reconstructions"][0]
