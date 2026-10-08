"""A video transect, with the stand-in network: a clip whose first half is
bright red (coral, to the stand-in) and second half dark (sand)."""

import csv
import json

import numpy as np
import pytest

pytest.importorskip("torch")
av = pytest.importorskip("av")

from iocean_cover.classes import Groups  # noqa: E402
from iocean_cover.video import transect  # noqa: E402

from test_segment import fake_segmenter  # noqa: E402


def clip(path, seconds=4, fps=10):
    with av.open(str(path), "w") as box:
        s = box.add_stream("mpeg4", rate=fps)
        s.width, s.height, s.pix_fmt = 128, 96, "yuv420p"
        for i in range(seconds * fps):
            image = np.zeros((96, 128, 3), np.uint8)
            if i < seconds * fps // 2:
                image[..., 0] = 250
            for packet in s.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                box.mux(packet)
        for packet in s.encode():
            box.mux(packet)


def test_cover_along_a_transect(tmp_path):
    clip(tmp_path / "t.mp4")
    seg = fake_segmenter()
    groups = Groups(seg.id2label, {"hard_coral": ["porites alive"], "sand": ["sand"], "not_seabed": ["unlabeled"]})
    said = transect(seg, groups, [tmp_path / "t.mp4"], tmp_path / "out", {"model": "fake"}, every=0.5,
                    begin=(27.0, 35.0), finish=(27.0, 35.001))
    assert said["frames"] == 8
    assert said["cover"]["hard_coral"] == pytest.approx(0.5, abs=0.13)
    assert 95 < said["lengthM"] < 105
    rows = list(csv.DictReader(open(tmp_path / "out" / "frames.csv")))
    assert float(rows[0]["hard_coral"]) > 0.9 and float(rows[-1]["sand"]) > 0.9
    assert float(rows[0]["longitude"]) == pytest.approx(35.0) and float(rows[-1]["longitude"]) > 35.0008
    assert json.loads((tmp_path / "out" / "transect.json").read_text())["framesUsed"] == 8
