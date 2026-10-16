from splat_pieces import Pieces, pieces_of


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
