"""Pictures of what model.py exported, so the design can be judged without
a CAD tool. A small z-buffer rasteriser: perspective, flat shading, one
colour per part, read from parts.json.

    hardware/.venv/bin/python hardware/nano/render.py [view ...]

Views: iso, rear, front, top, side, under, open (cover lifted off).
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import trimesh
from PIL import Image

import os
OUT = pathlib.Path(os.environ.get("RENDER_OUT", pathlib.Path(__file__).resolve().parents[1] / "out"))

# elevation, azimuth (degrees), from where the camera looks at the origin.
VIEWS = {
    "iso": (26, 35), "rear": (22, 150), "front": (8, 0), "top": (89, 0),
    "side": (0, 90), "under": (-40, 40), "open": (26, 35), "quarter": (18, -40),
}
W, H, SS = 1400, 1000, 2


def camera(elev: float, azim: float, distance: float):
    e, a = np.radians(elev), np.radians(azim)
    eye = distance * np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    forward = -eye / np.linalg.norm(eye)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return eye, forward, right, up


def rasterise(meshes, elev, azim):
    w, h = W * SS, H * SS
    all_v = np.concatenate([m.vertices for m, _ in meshes])
    centre = (all_v.min(0) + all_v.max(0)) / 2
    radius = np.linalg.norm(all_v - centre, axis=1).max()
    eye, fwd, right, up = camera(elev, azim, radius * 3.2)
    eye = eye + centre
    focal = 1.9 * w / 2
    colour = np.full((h, w, 3), 246, dtype=np.float32)
    depth = np.full((h, w), np.inf)
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    for mesh, rgba in meshes:
        rgb = np.array(rgba[:3], dtype=np.float32)
        alpha = rgba[3]
        v = mesh.vertices - eye
        cam = np.stack([v @ right, v @ up, v @ fwd], axis=1)
        z = cam[:, 2]
        px = w / 2 + focal * cam[:, 0] / z
        py = h / 2 - focal * cam[:, 1] / z
        normals = mesh.face_normals
        fill = np.array([-0.3, 0.6, -0.75])
        fill /= np.linalg.norm(fill)
        shade = 0.3 + 0.55 * np.clip(normals @ light, 0, 1) + 0.2 * np.clip(normals @ fill, 0, 1)
        faces = mesh.faces
        # Back-face culling on opaque parts keeps the insides out of the picture.
        facing = (mesh.face_normals @ (-fwd)) > -0.2 if alpha >= 0.99 else np.ones(len(faces), bool)
        for fi in np.nonzero(facing)[0]:
            i0, i1, i2 = faces[fi]
            x0, y0, x1, y1, x2, y2 = px[i0], py[i0], px[i1], py[i1], px[i2], py[i2]
            xmin, xmax = int(max(0, np.floor(min(x0, x1, x2)))), int(min(w - 1, np.ceil(max(x0, x1, x2))))
            ymin, ymax = int(max(0, np.floor(min(y0, y1, y2)))), int(min(h - 1, np.ceil(max(y0, y1, y2))))
            if xmin > xmax or ymin > ymax:
                continue
            det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(det) < 1e-9:
                continue
            xs, ys = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
            l1 = ((xs - x0) * (y2 - y0) - (x2 - x0) * (ys - y0)) / det
            l2 = ((x1 - x0) * (ys - y0) - (xs - x0) * (y1 - y0)) / det
            l0 = 1 - l1 - l2
            inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not inside.any():
                continue
            # Perspective-correct depth: interpolate 1/z, not z. Affine z put
            # the far corners of big flat triangles several millimetres too
            # near, and foam flush under a 2.5 mm skin punched through it.
            zz = 1.0 / (l0 / z[i0] + l1 / z[i1] + l2 / z[i2])
            win = depth[ymin:ymax + 1, xmin:xmax + 1]
            hit = inside & (zz < win)
            if not hit.any():
                continue
            c = rgb * shade[fi]
            block = colour[ymin:ymax + 1, xmin:xmax + 1]
            block[hit] = alpha * c + (1 - alpha) * block[hit]
            if alpha >= 0.99:
                win[hit] = zz[hit]
    image = Image.fromarray(np.clip(colour, 0, 255).astype(np.uint8))
    return image.resize((W, H), Image.LANCZOS)


def hexrgb(s: str):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def load(view: str):
    parts = json.loads((OUT / "parts.json").read_text())
    meshes = []
    order = sorted(parts, key=lambda n: parts[n].get("alpha", 1.0), reverse=True)  # opaque first
    for name in order:
        path = OUT / f"{name}.stl"
        if not path.exists():
            continue
        mesh = trimesh.load(path, force="mesh")
        if view == "open" and name == "cover":
            mesh.apply_translation((0, 0, 90))
        if view == "open" and name == "shell":
            mesh.apply_translation((0, 0, 110))
        if view == "open" and name == "ref-lid" and "cover" not in {p for p in parts}:
            mesh.apply_translation((0, 0, 90))
        rgb = hexrgb(parts[name]["colour"])
        meshes.append((mesh, (*rgb, parts[name].get("alpha", 1.0))))
    return meshes


def draw(view: str) -> pathlib.Path:
    elev, azim = VIEWS[view]
    image = rasterise(load(view), elev, azim)
    out = OUT / f"view-{view}.png"
    image.save(out)
    return out


if __name__ == "__main__":
    for view in (sys.argv[1:] or ["iso", "rear", "top", "open"]):
        print(draw(view))
