import numpy as np
import pytest

from iocean_cover import config
from iocean_cover.finetune import _batch
from iocean_cover.seaview import Quadrat, group_of


def test_points_move_with_their_image():
    rng = np.random.default_rng(3)
    image = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    xy = rng.uniform(0, 63, (40, 2)).astype(np.float32)
    q = Quadrat("q", "s", "BHS", image, xy, np.arange(40), np.ones(40, bool))
    for _ in range(20):
        images, points = _batch([q], 48, rng)
        rows, cols, g = points[0]
        for r, c, k in zip(rows, cols, g):
            x, y = np.round(xy[k]).astype(int)
            assert (images[0][r, c] == image[y, x]).all()


def test_every_caribbean_label_has_a_group():
    rules = config.load("finetune/caribbean-v1.yaml")["labels"]
    assert group_of("Mille", "Other Invertebrates", rules) == "hard_coral"
    assert group_of("OCOM-BL", "Hard Coral", rules) == "bleached_coral"
    assert group_of("GORG", "Soft Coral", rules) == "soft_coral"
    assert group_of("Dict", "Algae", rules) == "algae"
    assert group_of("CCA", "Algae", rules) == "hard_substrate"
    assert group_of("FISH", "Other", rules) == "not_seabed"
    with pytest.raises(ValueError):
        group_of("Mystery", "Other", rules)
