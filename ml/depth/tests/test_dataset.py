"""Reading a dataset back: features, targets, and a split that cannot leak."""

import json

import numpy as np

from iocean_depth.data import dataset as data


def chip(region, dataset, depth=-10.0, cells=8):
    x = np.full((7, cells, cells), 0.05, "float32")
    x[:, 0, 0] = np.nan                                       # a cloud nobody saw past
    y = np.full((cells, cells), depth, "float32")
    y[0, :] = np.nan                                          # a row the survey missed
    y[1, :] = 3.0                                             # land
    return {"region": region, "dataset": dataset, "x": x, "y": y}


def test_features_are_the_log_bands_the_ratio_and_where_input_is():
    f = data.features(chip("Florida", "a")["x"])
    assert f.shape == (len(data.FEATURES), 8, 8)
    assert np.isclose(f[2, 3, 3], np.log(0.05))
    assert np.isclose(f[7, 3, 3], np.log(50) / np.log(50))
    assert f[8, 0, 0] == 0 and f[8, 3, 3] == 1 and np.isfinite(f).all()


def test_only_measured_seabed_counts():
    depth, mask = data.target(chip("Florida", "a")["y"], 0.0, 40.0)
    assert not mask[0].any(), "nothing measured"
    assert not mask[1].any(), "land is not seabed"
    assert mask[2:].all() and np.allclose(depth[2:], 10.0)


def test_the_split_is_by_region_and_survey():
    rows = [chip("Florida", "a"), chip("USVI", "b"), chip("Florida", "c"), chip("Guam/CNMI", "d"),
            chip("Red Sea", "shushah")]
    parts = data.split(rows, ["USVI", "Guam/CNMI"], ["c"])
    assert [r["dataset"] for r in parts["train"]] == ["a"]
    assert [r["dataset"] for r in parts["validation"]] == ["c"]
    assert sorted(r["dataset"] for r in parts["test"]) == ["b", "d"]
    assert [r["dataset"] for r in parts["red-sea"]] == ["shushah"]
    held = {r["region"] for r in parts["test"]}
    assert not held & {r["region"] for r in parts["train"] + parts["validation"]}, "a held-out region leaked"


def test_augmenting_turns_input_and_label_together():
    x = np.arange(2 * 4 * 4, dtype="float32").reshape(2, 4, 4)
    y = x[0].copy()
    m = y > 3
    rng = np.random.default_rng(1)
    for _ in range(8):
        xa, ya, ma = data.augment(x, y, m, rng)
        assert np.array_equal(xa[0], ya) and np.array_equal(ma, ya > 3)


def test_chips_load_from_their_index(tmp_path):
    (tmp_path / "chips" / "florida").mkdir(parents=True)
    c = chip("Florida", "a")
    np.savez_compressed(tmp_path / "chips" / "florida" / "a-1.npz", x=c["x"], y=c["y"], kind="dense")
    (tmp_path / "chips" / "index.jsonl").write_text(json.dumps({"chip": "a-1", "file": "a-1.npz", "region": "Florida",
                                                                 "dataset": "a"}) + "\n")
    rows = data.load_chips(tmp_path)
    assert len(rows) == 1 and rows[0]["x"].shape == (7, 8, 8)


def test_a_survey_the_config_excludes_is_out_of_every_part():
    rows = [chip("Florida", "a"), chip("Am. Samoa", "samoa"), chip("USVI", "b")]
    parts = data.split(rows, ["USVI", "Am. Samoa"], [], excluded={"samoa": "ellipsoid heights"})
    assert not any(r["dataset"] == "samoa" for part in parts.values() for r in part)
    assert data.excluded_surveys({"lidar": [{"slug": "samoa", "excluded": "ellipsoid heights"}, {"slug": "a"}]}) == \
        {"samoa": "ellipsoid heights"}


def test_red_sea_areas_split_by_area_and_sparse_cells_can_count_more():
    rows = [chip("Florida", "a"), {**chip("Red Sea", "icesat-farasan"), "labelKind": "sparse"},
            {**chip("Red Sea", "icesat-thuwal"), "labelKind": "sparse"}]
    parts = data.split(rows, [], [], red_sea_train=["icesat-farasan"])
    assert [r["dataset"] for r in parts["train"]] == ["a", "icesat-farasan"]
    assert [r["dataset"] for r in parts["red-sea"]] == ["icesat-thuwal"]
    _, mask = zip(*(data.target(r["y"], 0.0, 40.0) for r in parts["train"]))
    w = data.weights(parts["train"], np.stack(mask), 10.0)
    assert w[0].max() == 1.0 and w[1].max() == 10.0
    assert w[1][~mask[1]].max() == 0, "an unmeasured cell counts for nothing"
