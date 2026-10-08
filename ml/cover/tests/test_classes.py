import numpy as np
import pytest

from iocean_cover import config
from iocean_cover.classes import Groups


def _id2label(cfg):
    names = sorted(n for labels in cfg["groups"].values() for n in labels if n != "unlabeled")
    return {0: "unlabeled", **{i + 1: n for i, n in enumerate(names)}}


def test_every_class_of_coralscapes_v2_is_in_one_group():
    cfg = config.load()
    id2label = _id2label(cfg)
    assert len(id2label) == 96                      # CoralscapesV2: void and 95 classes
    g = Groups(id2label, cfg["groups"])
    assert g.names[g.lookup[0]] == "not_seabed"


def test_a_class_left_out_or_twice_is_refused():
    cfg = config.load()
    id2label = _id2label(cfg)
    groups = {k: list(v) for k, v in cfg["groups"].items()}
    groups["sand"].append("rubble")
    with pytest.raises(ValueError, match="both"):
        Groups(id2label, groups)
    groups = {k: list(v) for k, v in cfg["groups"].items()}
    groups["sand"] = []
    with pytest.raises(ValueError, match="in no group"):
        Groups(id2label, groups)


def test_shares_leave_out_what_is_not_seabed():
    id2label = {0: "unlabeled", 1: "porites alive", 2: "sand", 3: "fish"}
    g = Groups(id2label, {"hard_coral": ["porites alive"], "sand": ["sand"], "not_seabed": ["unlabeled", "fish"]})
    classes = np.array([[1, 2, 2, 3], [3, 3, 0, 0]])
    s = g.shares(classes)
    assert s == {"hard_coral": pytest.approx(1 / 3), "sand": pytest.approx(2 / 3)}
    assert g.shares(np.array([[3, 0]])) is None
