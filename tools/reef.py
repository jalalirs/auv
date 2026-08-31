"""Putting coral where coral would be.

Not scattered evenly. Reef-building coral needs light, so it thins with depth
and stops altogether below about twenty-five metres. It needs something to hold
to, so it prefers slope and rock over flat sand, but not a cliff. And it grows
in patches with clearings between them, so an even lawn of it reads as carpet.

Every colony is grown, so no two are the same, and they are placed through a
point instancer: forty thousand colonies cost what thirty do, because thirty is
how many distinct ones there are.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np

import coral


def plant(where: pathlib.Path, height, across: float, seed: int,
          how_many: int) -> dict:
    """Grow a reef onto a seabed, and write it beside it."""
    rng = np.random.default_rng(seed)
    rows, columns = height.shape

    depth = -height
    dy, dx = np.gradient(height.astype("float64"),
                         across / max(1, rows - 1), across / max(1, columns - 1))
    slope = np.hypot(dx, dy)

    # Light: full to about eight metres, gone by twenty-five.
    lit = np.clip((25.0 - depth) / 17.0, 0.0, 1.0) ** 1.5
    lit[depth < 0.8] = 0.0        # too shallow — it dries and gets broken up

    # Something to hold to. A little slope is good; a cliff is not.
    hold = np.clip(slope * 3.2, 0.15, 1.0) * np.clip(1.6 - slope, 0.2, 1.0)

    # Patchiness. Low-frequency noise, smoothed, leaves the clearings a real
    # reef has instead of covering everything at one density.
    coarse = rng.random((max(2, rows // 12), max(2, columns // 12)))
    for _ in range(3):
        coarse = 0.25 * (np.roll(coarse, 1, 0) + np.roll(coarse, -1, 0)
                         + np.roll(coarse, 1, 1) + np.roll(coarse, -1, 1))
    # Resampled by index rather than tiled, because a tiling only lands on the
    # right shape when the size divides exactly and otherwise fails loudly at
    # the first multiply.
    up_rows = (np.arange(rows) * coarse.shape[0] // max(1, rows)).clip(0, coarse.shape[0] - 1)
    up_columns = (np.arange(columns) * coarse.shape[1] // max(1, columns)).clip(0, coarse.shape[1] - 1)
    patch = coarse[np.ix_(up_rows, up_columns)]
    spread = float(patch.max() - patch.min()) or 1.0
    patch = (patch - patch.min()) / spread

    want = lit * hold * (0.25 + 1.5 * patch)
    if want.sum() <= 0:
        return {"colonies": 0}

    flat = (want / want.sum()).ravel()
    picked = rng.choice(flat.size, size=how_many, p=flat)
    row, column = np.unravel_index(picked, want.shape)

    step_x = across / max(1, columns - 1)
    step_y = across / max(1, rows - 1)
    x = -across / 2 + column * step_x + rng.uniform(-step_x / 2, step_x / 2, how_many)
    y = -across / 2 + row * step_y + rng.uniform(-step_y / 2, step_y / 2, how_many)
    z = height[row, column] - 0.04    # bedded in, not balanced on top

    kinds = [k for k, _ in coral.COMMUNITY]
    weights = np.array([w for _, w in coral.COMMUNITY], dtype=float)
    weights /= weights.sum()

    sizes = {"branching": 0.75, "massive": 0.55, "table": 0.34,
             "brain": 0.45, "fan": 0.85, "finger": 0.5}
    variants = 5
    prototypes, colours = [], []
    for kind in kinds:
        for _ in range(variants):
            prototypes.append(
                coral.grow_one(kind, rng, sizes[kind] * rng.uniform(0.7, 1.4)))
            colours.append(coral.PALETTE[int(rng.integers(0, len(coral.PALETTE)))])

    which_kind = rng.choice(len(kinds), size=how_many, p=weights)
    which = which_kind * variants + rng.integers(0, variants, how_many)

    scale = rng.uniform(0.55, 1.7, how_many)
    # Larger colonies where it is shallower and brighter, which is true, and
    # also puts the big tables where they will actually be seen.
    scale = scale * np.clip(1.25 - depth[row, column] / 30.0, 0.5, 1.25)
    turn = rng.uniform(0, 2 * math.pi, how_many)

    (where / "coral.usda").write_text(
        _instancer(prototypes, colours, x, y, z, which, scale, turn))
    return {"colonies": int(how_many), "prototypes": len(prototypes),
            "points": int(sum(len(p) for p, _ in prototypes))}


def _triples(values) -> str:
    return ", ".join("(%.4g, %.4g, %.4g)" % (a, b, c) for a, b, c in values)


def _instancer(prototypes, colours, x, y, z, which, scale, turn) -> str:
    """The reef, as one instancer over a handful of grown prototypes."""
    grown = []
    for i, ((points, faces), colour) in enumerate(zip(prototypes, colours)):
        counts = ", ".join(["3"] * len(faces))
        indices = ", ".join(str(v) for v in faces.reshape(-1))
        grown.append(
            '\n        def Mesh "Coral_%d"\n        {\n'
            '            uniform token subdivisionScheme = "none"\n'
            "            int[] faceVertexCounts = [%s]\n"
            "            int[] faceVertexIndices = [%s]\n"
            "            point3f[] points = [%s]\n"
            "            color3f[] primvars:displayColor = [(%.3g, %.3g, %.3g)] (\n"
            '                interpolation = "constant"\n'
            "            )\n"
            "        }\n" % (i, counts, indices, _triples(points),
                             colour[0], colour[1], colour[2]))

    # Turned about the vertical, as a quaternion — one line rather than a
    # matrix for every colony.
    half = turn / 2.0
    orient = np.stack([np.cos(half), np.zeros_like(half),
                       np.zeros_like(half), np.sin(half)], axis=-1)

    return (
        "#usda 1.0\n"
        "(\n"
        '    doc = "Coral, grown rather than scanned. Metres, Z up."\n'
        '    defaultPrim = "Coral"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Z"\n'
        ")\n\n"
        'def PointInstancer "Coral"\n'
        "{\n"
        "    point3f[] positions = [%s]\n"
        "    int[] protoIndices = [%s]\n"
        "    float3[] scales = [%s]\n"
        "    quath[] orientations = [%s]\n"
        "    rel prototypes = [%s]\n\n"
        '    def Scope "Grown"\n'
        "    {%s    }\n"
        "}\n" % (
            _triples(np.stack([x, y, z], axis=-1)),
            ", ".join(str(int(i)) for i in which),
            _triples(np.stack([scale, scale, scale], axis=-1)),
            ", ".join("(%.5g, %.5g, %.5g, %.5g)" % (w, a, b, c)
                      for w, a, b, c in orient),
            ", ".join("</Coral/Grown/Coral_%d>" % i for i in range(len(prototypes))),
            "".join(grown)))
