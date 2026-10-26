from splat_pieces import Pieces, all_pieces, pieces_of, prim_path


def _three():
    return Pieces([
        {"prim": "Part0", "path": [[x, 0, 0] for x in range(0, 10)]},
        {"prim": "Part1", "path": [[x, 0, 0] for x in range(10, 20)]},
        {"prim": "Part2", "path": [[x, 0, 0] for x in range(20, 30)]},
    ])


def test_the_piece_whose_stretch_is_nearest():
    pieces = _three()
    assert pieces.which([2, 1, 0]) == 0
    assert pieces.which([15, -2, 1]) == 1
    assert pieces.which([29, 0, 0]) == 2


def test_a_boundary_does_not_flip_back_and_forth():
    pieces = _three()
    assert pieces.which([8, 0, 0]) == 0
    # Just past the boundary: piece 1 is nearer, but not by the margin.
    assert pieces.which([9.6, 0, 0]) == 0
    assert pieces.which([9.4, 0, 0]) == 0
    # Well into the next stretch it changes, and holds there.
    assert pieces.which([11, 0, 0]) == 1
    assert pieces.which([9.6, 0, 0]) == 1


def test_a_place_without_pieces_has_none():
    assert pieces_of({}) is None
    assert pieces_of({"reef": {"splats": {"file": "splats.usdz"}}}) is None
    assert pieces_of({"reef": {"splats": {"pieces": [{"prim": "Part0", "path": [[0, 0, 0]]}]}}}) is None
    found = pieces_of({"reef": {"splats": {"pieces": [{"prim": "A", "path": [[0, 0, 0]]},
                                                      {"prim": "B", "path": [[5, 0, 0]]}]}}})
    assert found.prims == ["A", "B"]


def test_a_reconstruction_laid_into_a_place_brings_its_own():
    site = {"reef": {"splats": {"pieces": [{"prim": "Part0", "path": [[0, 0, 0]]}, {"prim": "Part1", "path": [[9, 0, 0]]}]}},
            "reconstructions": [{"name": "video", "pieces": [
                {"prim": "/World/Reconstructions/video/Part0", "path": [[100, 0, 0]]},
                {"prim": "/World/Reconstructions/video/Part1", "path": [[110, 0, 0]]}]}]}
    groups = all_pieces(site)
    assert [g.prims[0] for g in groups] == ["Part0", "/World/Reconstructions/video/Part0"]
    assert prim_path("Part1") == "/World/Coral/Splats/Part1"
    assert prim_path("/World/Reconstructions/video/Part1") == "/World/Reconstructions/video/Part1"
    assert all_pieces({}) == []


def test_splats_fade_into_the_water_with_distance():
    from splat_pieces import CARRIED_M, haze_rows
    lengths, veil = (2.0, 8.0, 12.0), (0.1, 0.3, 0.35)
    near = haze_rows(CARRIED_M, lengths, veil)
    assert near == ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    far = haze_rows(40.0, lengths, veil)
    # Red goes first, blue last, and what goes is replaced by the veil.
    assert far[0][0] < far[1][1] < far[2][2] < 0.1
    assert abs(far[0][3] - 0.1) < 1e-3 and abs(far[2][3] - 0.35 * (1 - far[2][2])) < 1e-4


def test_distance_to_a_box():
    from splat_pieces import distance_to_box
    assert distance_to_box([0, 0, 0], [-1, -1, -1], [1, 1, 1]) == 0.0
    assert abs(distance_to_box([4, 0, 5], [-1, -1, -1], [1, 1, 1]) - 5.0) < 1e-9
