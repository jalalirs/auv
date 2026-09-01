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
    hold = np.clip(0.45 + slope * 2.6, 0.35, 1.0) * np.clip(1.6 - slope, 0.2, 1.0)

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

    # Thickets, not a sprinkle. Raising the patch term concentrates colonies
    # into stands with clear sand between them, which is how a reef is built
    # and also what makes it read as one: continuous cover somewhere, rather
    # than uniform scatter everywhere.
    want = lit * hold * (0.02 + 3.2 * patch ** 3.0)
    if want.sum() <= 0:
        return {"colonies": 0}

    # In stands, not sprinkled.
    #
    # Coral recruits next to coral: a colony breaks, the fragment lands beside
    # it and grows, and the reef builds outward from what is already there. So
    # places are chosen for a thicket and colonies are dropped around each one,
    # which is what makes cover continuous somewhere instead of thin everywhere.
    # Big stands, tightly packed. A reef's cover is continuous where it is
    # present and absent where it is not; the failure mode to avoid is thin
    # everywhere, which reads as ornaments on a beach.
    per_stand = 26
    stands = max(1, how_many // per_stand)
    flat = (want / want.sum()).ravel()
    picked = rng.choice(flat.size, size=stands, p=flat)
    row, column = np.unravel_index(picked, want.shape)

    step_x = across / max(1, columns - 1)
    step_y = across / max(1, rows - 1)
    centre_x = -across / 2 + column * step_x
    centre_y = -across / 2 + row * step_y

    # Every colony belongs to a stand, and sits within a couple of metres of it.
    belongs = np.repeat(np.arange(stands), per_stand)[:how_many]
    if belongs.size < how_many:
        belongs = np.concatenate([belongs, rng.integers(0, stands, how_many - belongs.size)])
    spread = rng.normal(0, 1.15, (how_many, 2))
    x = centre_x[belongs] + spread[:, 0]
    y = centre_y[belongs] + spread[:, 1]
    x = np.clip(x, -across / 2, across / 2)
    y = np.clip(y, -across / 2, across / 2)

    # Sat on the seabed under wherever it actually landed, not under the middle
    # of its stand — a colony two metres away can be half a metre lower.
    at_column = np.clip(((x + across / 2) / step_x).astype(int), 0, columns - 1)
    at_row = np.clip(((y + across / 2) / step_y).astype(int), 0, rows - 1)
    z = height[at_row, at_column] - 0.04   # bedded in, not balanced on top
    row, column = at_row, at_column

    kinds = [k for k, _ in coral.COMMUNITY]
    weights = np.array([w for _, w in coral.COMMUNITY], dtype=float)
    weights /= weights.sum()

    # Colonies the size colonies are. The first pass grew them at a third of
    # this and the reef read as gravel with twigs in it.
    sizes = {"branching": 1.15, "massive": 0.85, "table": 0.55,
             "brain": 0.75, "fan": 1.10, "finger": 0.80,
             "rubble": 0.34, "encrusting": 0.30}
    variants = 6
    prototypes, colours = [], []
    for kind in kinds:
        for _ in range(variants):
            prototypes.append(
                coral.grow_one(kind, rng, sizes[kind] * rng.uniform(0.7, 1.4)))
            colours.append(coral.a_colour(rng, kind))

    which_kind = rng.choice(len(kinds), size=how_many, p=weights)
    which = which_kind * variants + rng.integers(0, variants, how_many)

    # Scaled by kind. A table two metres across is a table; the same multiplier
    # on a plate that is already three metres wide gives a seven metre sheet,
    # and a handful of those fill the view and read as scenery flats.
    per_kind = np.array([{"branching": 1.0, "rubble": 1.0, "encrusting": 0.42,
                          "finger": 1.0, "massive": 0.9, "table": 0.55,
                          "brain": 0.9, "fan": 1.0}[k] for k in kinds])
    scale = rng.uniform(0.65, 1.8, how_many) * per_kind[which_kind]
    # Larger colonies where it is shallower and brighter, which is true, and
    # also puts the big tables where they will actually be seen.
    scale = scale * np.clip(1.25 - depth[row, column] / 30.0, 0.5, 1.25)
    turn = rng.uniform(0, 2 * math.pi, how_many)

    (where / "coral.usda").write_text(
        _instancer(prototypes, colours, x, y, z, which, scale, turn))
    return {"colonies": int(how_many), "prototypes": len(prototypes),
            "points": int(sum(len(p) for p, _ in prototypes))}


def _smooth_normals(points, faces):
    """Vertex normals, averaged from the faces that meet there.

    Without them a colony is shaded facet by facet and a boulder coral looks
    like a cut gem — which is what the first dense reef looked like: right
    shapes, right colours, and every one of them a polyhedron.
    """
    normals = np.zeros_like(points, dtype="float64")
    a, b, c = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]
    face = np.cross(b - a, c - a)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length < 1e-12] = 1.0
    return normals / length


def _triples(values) -> str:
    return ", ".join("(%.4g, %.4g, %.4g)" % (a, b, c) for a, b, c in values)


def _skins(colours) -> str:
    """A material per prototype.

    A mesh carrying only a display colour gets flat shading, and under a bright
    sun every colony comes out chalk-white — which is what the first reef looked
    like: correct shapes, correct places, and the colour of bone.
    """
    skins = []
    for i, colour in enumerate(colours):
        skins.append(
            '        def Material "Skin_%d"\n        {\n'
            "            token outputs:surface.connect = "
            "</Coral/Skins/Skin_%d/Surface.outputs:surface>\n"
            '            def Shader "Surface"\n            {\n'
            '                uniform token info:id = "UsdPreviewSurface"\n'
            "                color3f inputs:diffuseColor = (%.3g, %.3g, %.3g)\n"
            "                float inputs:roughness = 0.82\n"
            "                float inputs:metallic = 0\n"
            "                token outputs:surface\n"
            "            }\n        }\n" % (i, i, colour[0], colour[1], colour[2]))
    return '    def Scope "Skins"\n    {\n%s    }\n' % "".join(skins)


def _instancer(prototypes, colours, x, y, z, which, scale, turn) -> str:
    """The reef, as one instancer over a handful of grown prototypes."""
    grown = []
    for i, ((points, faces), colour) in enumerate(zip(prototypes, colours)):
        counts = ", ".join(["3"] * len(faces))
        indices = ", ".join(str(v) for v in faces.reshape(-1))
        grown.append(
            '\n        def Mesh "Coral_%d" (\n'
            '            prepend apiSchemas = ["MaterialBindingAPI"]\n'
            "        )\n        {\n"
            '            uniform token subdivisionScheme = "none"\n'
            "            int[] faceVertexCounts = [%s]\n"
            "            int[] faceVertexIndices = [%s]\n"
            "            point3f[] points = [%s]\n"
            "            normal3f[] normals = [%s] (\n"
            '                interpolation = "vertex"\n'
            "            )\n"
            "            color3f[] primvars:displayColor = [(%.3g, %.3g, %.3g)] (\n"
            '                interpolation = "constant"\n'
            "            )\n"
            "            rel material:binding = </Coral/Skins/Skin_%d>\n"
            "        }\n" % (i, counts, indices, _triples(points),
                             _triples(_smooth_normals(points, faces)),
                             colour[0], colour[1], colour[2], i))

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
        "%s\n"
        "    point3f[] positions = [%s]\n"
        "    int[] protoIndices = [%s]\n"
        "    float3[] scales = [%s]\n"
        "    quath[] orientations = [%s]\n"
        "    rel prototypes = [%s]\n\n"
        '    def Scope "Grown"\n'
        "    {%s    }\n"
        "}\n" % (
            _skins(colours),
            _triples(np.stack([x, y, z], axis=-1)),
            ", ".join(str(int(i)) for i in which),
            _triples(np.stack([scale, scale, scale], axis=-1)),
            ", ".join("(%.5g, %.5g, %.5g, %.5g)" % (w, a, b, c)
                      for w, a, b, c in orient),
            ", ".join("</Coral/Grown/Coral_%d>" % i for i in range(len(prototypes))),
            "".join(grown)))
