"""A dive's disturbance, as rows that each say what they are."""

import disturbance


def test_every_row_says_it_was_computed_and_from_what():
    rows = disturbance.rows(
        {"fish": 40, "fledTheVehicle": 7, "bumped": 1},
        {"colonies": 12, "struck": 2, "brushed": 3, "broken": [{"kind": "branching"}], "from": "the place",
         "smothered": 1, "smotheredBadly": 0, "disturbed": 4},
        {"liftedG": 3.5, "settledG": 2.0, "worstOnACoralMgCm2": 0.4, "worstVisibilityM": 6.1, "from": "derived: x"},
        {"ground": 2})
    said = {r["what"]: r for r in rows}
    assert said["fish put to flight by the vehicle"]["value"] == 7
    assert said["fish put to flight by the vehicle"]["unit"] == "of 40"
    assert said["colonies broken"]["value"] == 1
    assert said["colonies that shut their polyps"]["value"] == 4
    assert said["sand lifted"]["value"] == 3.5
    assert said["times it touched the ground"]["value"] == 2
    assert all(r["kind"] == "derived" and r["from"] for r in rows)


def test_nothing_there_says_nothing():
    assert disturbance.rows(None, None, None, None) == []
    assert [r["what"] for r in disturbance.rows(None, None, None, {"ground": 0})] == ["times it touched the ground"]


def test_the_counted_share_needs_its_twin():
    assert disturbance.counted_share(5, 0) is None
    share = disturbance.counted_share(39, 50)
    assert share["value"] == 0.78 and share["unit"] == "39 of 50" and share["kind"] == "derived"
