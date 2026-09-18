"""A picture of what model.py exported, so it can be judged without a CAD tool.

    hardware/.venv/bin/python hardware/nano/render.py [view ...]

Views: iso, front, top, side, open (the top half lifted off).
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out"

VIEWS = {
    "iso": (28, -50), "rear": (24, 135), "front": (0, 0), "top": (90, 0), "side": (0, -90), "open": (28, -50),
}
PARTS = [
    ("shell-top", "#c9c9c9"), ("shell-bottom", "#b0b0b0"),
    ("ref-hull", "#6fa8dc"), ("ref-thrusters", "#333333"),
]


def draw(view: str) -> pathlib.Path:
    elev, azim = VIEWS[view]
    fig = plt.figure(figsize=(9, 7), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for name, colour in PARTS:
        path = OUT / f"{name}.stl"
        if not path.exists():
            continue
        mesh = trimesh.load(path, force="mesh")
        # The painter's algorithm sorts whole triangles; a big flat one on the
        # top ends up drawn over the ducts. Small triangles sort honestly.
        mesh = mesh.subdivide_to_size(max_edge=6.0)
        v = mesh.vertices.copy()
        if view == "open" and name == "shell-top":
            v[:, 2] += 80
        tris = v[mesh.faces]
        poly = Poly3DCollection(tris, alpha=0.95 if "ref" not in name else 0.8)
        poly.set_facecolor(colour)
        poly.set_edgecolor("none")
        ax.add_collection3d(poly)
        lo, hi = np.minimum(lo, v.min(0)), np.maximum(hi, v.max(0))
    centre, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(centre[0] - span, centre[0] + span)
    ax.set_ylim(centre[1] - span, centre[1] + span)
    ax.set_zlim(centre[2] - span, centre[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(f"nano · {view}  (x forward is +x)")
    out = OUT / f"view-{view}.png"
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


if __name__ == "__main__":
    for view in (sys.argv[1:] or ["iso", "open", "front"]):
        print(draw(view))
