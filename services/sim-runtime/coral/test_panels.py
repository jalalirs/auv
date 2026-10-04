"""The water's push on a hull, panel by panel (panels.py)."""

import itertools
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from panels import Panels  # noqa: E402


def directions():
    out = np.array([d for d in itertools.product((-1, 0, 1), repeat=3) if any(d)], dtype=float)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def a_plate(area=1.0, arm=0.0):
    """A flat plate facing ahead: its front face and its back face, both open."""
    ways = directions()
    return Panels({"centresM": [[0, arm, 0], [0, arm, 0]], "normals": [[1, 0, 0], [-1, 0, 0]],
                   "areasM2": [area, area], "directions": ways.tolist(),
                   "exposed": np.ones((len(ways), 2)).tolist(), "wakeShare": 0.5})


def test_a_plate_has_a_plates_drag():
    """Front and back together are Hoerner's 1.17 for a plate square to the flow."""
    drag = -a_plate().wrench(np.array([1.0, 0, 0, 0, 0, 0]), 1000.0)[0]
    assert abs(drag - 0.5 * 1000.0 * 1.17) < 1.0


def test_a_turn_is_damped_by_what_its_ends_sweep():
    plate = a_plate(arm=1.0)
    yaw = plate.wrench(np.array([0, 0, 0, 0, 0, 0.5]), 1000.0)[5]
    assert yaw < 0.0, "a turn the other way is what the water does back"


def test_a_shielded_face_meets_slowed_water():
    plate = a_plate()
    plate.open[:, 0] = 0.0                     # the front face behind something
    drag = -plate.wrench(np.array([1.0, 0, 0, 0, 0, 0]), 1000.0)[0]
    assert abs(drag - 0.5 * 1000.0 * (0.8 * 0.25 + 0.37)) < 1.0


def test_the_heavy_package_carries_its_panels():
    package = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2-heavy"
    panels = Panels.of(package)
    assert panels is not None and len(panels.area) > 500
    surge = -panels.wrench(np.array([1.0, 0, 0, 0, 0, 0]), 1025.0)[0]
    assert 40.0 < surge < 50.0, "fitted to Li et al.'s 45 N at a metre a second"
    assert json.loads((package / "panels.json").read_text())["from"].startswith("derived")
