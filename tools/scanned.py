"""Colonies somebody scanned, rather than colonies somebody grew.

Every coral on this platform is a procedural shape: a blob roughened by noise,
correct in size and place and not in form. Take the water away and they read as
painted stones, which is what they are.

There is a real one in the repository and there has been since September. The
Smithsonian publishes its coral type specimens under CC0 and serves them
through an API that needs no account, and `tools/reference` fetched one:
`usnm_58_orbicella_coronata.glb`, a hundred thousand triangles with UVs,
normals and three texture maps. It sat unused while every frame was drawn with
blobs.

**What a scan gives and what it does not.** These are museum specimens: dry
skeletons, bleached, mounted. So they give the *form* — the corallite
structure, the growth banding, the way a mounding coral is actually lumpy
rather than smoothly noisy — and they give nothing about colour, because the
tissue that had the colour is long gone. Colour stays where it already is: the
palette taken from photographs of each reef.

**And they are not a replacement for the grown ones.** A single specimen is one
colony that happened to be collected, and a reef is variation. Scans go in for
the kinds somebody has scanned; the growers stay for everything else and for
the spread within a species that one specimen cannot express.
"""

from __future__ import annotations

import json
import math
import pathlib
import struct

import numpy as np


def read_glb(path: pathlib.Path):
    """Points and triangles out of a binary glTF, in its own units."""
    raw = path.read_bytes()
    magic, version, _ = struct.unpack("<III", raw[:12])
    if magic != 0x46546C67:
        raise ValueError(f"{path.name} is not a glb")
    at, described, buffer = 12, None, None
    while at + 8 <= len(raw):
        length, kind = struct.unpack("<II", raw[at:at + 8])
        chunk = raw[at + 8:at + 8 + length]
        if kind == 0x4E4F534A:
            described = json.loads(chunk)
        elif kind == 0x004E4942:
            buffer = chunk
        at += 8 + length + (-length % 4)
    if described is None or buffer is None:
        raise ValueError(f"{path.name} has no geometry")

    def read(index: int) -> np.ndarray:
        accessor = described["accessors"][index]
        view = described["bufferViews"][accessor["bufferView"]]
        kind = {5121: "<u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[
            accessor["componentType"]]
        wide = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        count = accessor["count"] * wide
        flat = np.frombuffer(buffer, dtype=kind, count=count, offset=start)
        return flat.reshape(-1, wide) if wide > 1 else flat

    points, faces, at_vertex = [], [], 0
    for mesh in described.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "POSITION" not in prim.get("attributes", {}):
                continue
            here = np.asarray(read(prim["attributes"]["POSITION"]), dtype=float)
            index = np.asarray(read(prim["indices"]), dtype=np.int64).reshape(-1, 3)
            points.append(here)
            faces.append(index + at_vertex)
            at_vertex += len(here)
    if not points:
        raise ValueError(f"{path.name} has no positions")
    return np.vstack(points), np.vstack(faces)


def simplify(points: np.ndarray, faces: np.ndarray, most: int):
    """Fewer triangles, by welding vertices that share a cell of a grid.

    Vertex clustering: lay a grid over the object, move every vertex to the
    average of its cell, and drop the triangles that collapse. It is not the
    best decimator — an edge-collapse driven by error keeps a silhouette
    better — and it is uniform, which is the property that matters here.

    The first version kept the largest triangles instead, which sounds
    equivalent and is not: the largest triangles on a scan are the flat ones,
    so it kept a slab and threw away half the depth of the object. The span
    across the specimen went from eleven centimetres to five and the shape it
    produced was a shape nothing ever grew.

    It is here because a hundred thousand triangles is a lot for one colony
    seen from three metres, and a reef is sixty prototypes.
    """
    if len(faces) <= most:
        return points, faces

    span = np.ptp(points, axis=0)
    widest = float(span.max())
    if widest <= 0.0:
        return points, faces

    # How coarse the grid has to be to land near the triangle count asked for
    # is not something to work out in closed form, because it depends on how
    # the surface folds. Search for it: double the grid until it overshoots,
    # then bisect. Ten welds on a hundred thousand triangles is milliseconds.
    low, high = 2, 4
    while high < 1024 and len(_weld(points, faces, widest, high)[1]) < most:
        low, high = high, high * 2
    for _ in range(12):
        if high - low <= 1:
            break
        middle = (low + high) // 2
        if len(_weld(points, faces, widest, middle)[1]) > most:
            high = middle
        else:
            low = middle
    return _weld(points, faces, widest, low)


def _weld(points: np.ndarray, faces: np.ndarray, widest: float, cells: int):
    """One pass of the clustering, on a grid `cells` across at its widest."""
    step = widest / cells
    at = np.floor((points - points.min(axis=0)) / step).astype(np.int64)

    _, belongs = np.unique(at, axis=0, return_inverse=True)
    welded = np.zeros((int(belongs.max()) + 1, 3), dtype=float)
    counted = np.zeros(len(welded))
    np.add.at(welded, belongs, points)
    np.add.at(counted, belongs, 1.0)
    welded /= counted[:, None]

    kept = belongs[faces]
    # A triangle whose corners landed in the same cell is no longer a triangle.
    alive = ((kept[:, 0] != kept[:, 1]) & (kept[:, 1] != kept[:, 2])
             & (kept[:, 0] != kept[:, 2]))
    kept = np.unique(np.sort(kept[alive], axis=1), axis=0) if len(kept[alive]) else kept[alive]
    kept = kept.astype(np.int64)
    used = np.unique(kept) if len(kept) else np.array([], dtype=np.int64)
    renumber = np.full(len(welded), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    return welded[used], renumber[kept]


def as_a_colony(path: pathlib.Path, size: float, most: int = 6000):
    """One scan, ready to stand on a seabed at about `size` metres across.

    Museum scans arrive in whatever units and whatever orientation the scanner
    had. So: centred on its own footprint, sat with its lowest point at zero,
    and scaled to the size the reef asked for — which is the size the survey
    said, not the size the specimen happened to be.
    """
    points, faces = read_glb(path)
    points, faces = simplify(points, faces, most)

    # glTF is Y-up; this platform is Z-up.
    points = np.column_stack([points[:, 0], -points[:, 2], points[:, 1]])

    span = np.ptp(points[:, :2], axis=0).max()
    if span > 1e-9:
        points = points * (float(size) / float(span))
    points[:, :2] -= points[:, :2].mean(axis=0)
    points[:, 2] -= points[:, 2].min()
    return points, faces


def found_in(reference: pathlib.Path) -> dict:
    """Which kinds have a scan, from a reference directory's assets.

    Named by what the file says it is. A specimen nobody can identify is a
    specimen nobody should be placing on a reef as though they could.
    """
    assets = reference / "assets"
    if not assets.is_dir():
        return {}
    # Which growth form each genus takes. Only genera somebody has actually
    # scanned appear here, and each is what a reef scientist would call it.
    forms = {
        "orbicella": "massive", "montastraea": "massive", "porites": "massive",
        "siderastrea": "brain", "diploria": "brain", "colpophyllia": "brain",
        "acropora": "branching", "pocillopora": "branching",
        "millepora": "encrusting", "agaricia": "table",
    }
    found: dict[str, pathlib.Path] = {}
    for one in sorted(assets.glob("*.glb")):
        name = one.stem.lower()
        for genus, form in forms.items():
            if genus in name:
                found.setdefault(form, one)
                break
    return found
