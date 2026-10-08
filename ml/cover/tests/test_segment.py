"""The windowing, with a stand-in for the network: it says class 1 where the
red channel is bright and class 2 elsewhere, at a quarter of the resolution as
SegFormer does. Blended over windows, the result must still follow the image."""

import types

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from iocean_cover.segment import Segmenter, _starts, gather_matrix  # noqa: E402
from iocean_cover.classes import Groups  # noqa: E402


class Fake(torch.nn.Module):
    def forward(self, pixel_values):
        red = torch.nn.functional.avg_pool2d(pixel_values[:, :1], 4) - 0.5
        logits = torch.cat([torch.full_like(red, -100.0), red * 20, -red * 20], 1)
        return types.SimpleNamespace(logits=logits)


def fake_segmenter(window=64, stride=48):
    s = Segmenter.__new__(Segmenter)
    s.device, s.model = "cpu", Fake()
    s.mean = torch.zeros(3)[:, None, None]
    s.std = torch.ones(3)[:, None, None]
    s.id2label = {0: "unlabeled", 1: "porites alive", 2: "sand"}
    s.window, s.stride, s.batch = window, stride, 3
    return s


def test_windows_cover_the_image_and_end_flush():
    assert _starts(100, 64, 48) == [0, 36]
    assert _starts(64, 64, 48) == [0]
    assert _starts(10, 64, 48) == [0]
    s = _starts(1000, 64, 48)
    assert s[-1] == 1000 - 64 and all(b - a <= 48 for a, b in zip(s, s[1:]))


@pytest.mark.parametrize("shape", [(200, 330), (40, 50)])
def test_blended_windows_follow_the_image(shape):
    rng = np.random.default_rng(0)
    image = np.zeros(shape + (3,), np.uint8)
    image[: shape[0] // 2, : shape[1] // 3, 0] = 245              # a bright block, class 1
    image += rng.integers(0, 10, image.shape, dtype=np.uint8)      # noise, short of wrapping round
    classes = fake_segmenter().classes(image)
    assert classes.shape == shape
    inner = np.zeros(shape, bool)
    inner[: shape[0] // 2 - 4, : shape[1] // 3 - 4] = True
    outer = np.ones(shape, bool)
    outer[: shape[0] // 2 + 4, : shape[1] // 3 + 4] = False
    assert (classes[inner] == 1).all() and (classes[outer] == 2).all()


def test_gathered_probabilities_sum_to_one():
    s = fake_segmenter()
    g = Groups(s.id2label, {"hard_coral": ["porites alive"], "sand": ["sand"], "not_seabed": ["unlabeled"]})
    p = s.probabilities(np.full((90, 70, 3), 128, np.uint8), into=gather_matrix(g, s.id2label))
    assert p.shape == (3, 90, 70)
    assert torch.allclose(p.sum(0), torch.ones(90, 70), atol=1e-4)
