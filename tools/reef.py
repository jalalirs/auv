"""Putting coral where coral would be.

Where each square metre of ground can hold is worked out in zonation.py, from
light, wave energy and whether the ground is rock or sand. What is here is the
planting: how many colonies that cover needs, which of them go where, and what
shape each one is.

Two things changed after the first reef was flown over and looked at from
above. Colonies used to be drawn from one mix for the whole site, which put
staghorn thickets on the crest where the waves break them and boulder heads at
thirty metres where there is no light to build them with; they are now drawn
from the mix for the depth they landed at. And the count used to be given, with
the resulting cover discovered afterwards; it is now worked out from the cover
that is wanted and the size the colonies actually came out, because cover goes
as count times size squared and nobody estimates that correctly by looking.

Every colony is grown, so no two are the same, and they are placed through a
point instancer: a million colonies cost what fifty do, because fifty is how
many distinct ones there are.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np

import coral
import zonation


def plant(where: pathlib.Path, height, across: float, seed: int,
          how_many: int) -> dict:
    """Grow a reef onto a seabed, and write it beside it."""
    rng = np.random.default_rng(seed)
    rows, columns = height.shape
    depth = -height

    # What kind of ground this is, everywhere.
    ground = zonation.describe(height, across)
    want = zonation.cover(ground, rng)
    if want.sum() <= 0:
        return {"colonies": 0}

    step_x = across / max(1, columns - 1)
    step_y = across / max(1, rows - 1)

    # How solid each kind is inside its own outline. A branching colony's
    # extent is mostly gaps — you can see the sand through it — and counting its
    # bounding ellipse as covered ground overstates a staghorn thicket by about
    # three times. A boulder is nearly all boulder.
    solidity = {"branching": 0.32, "fan": 0.18, "finger": 0.55, "massive": 0.88,
                "brain": 0.90, "table": 0.80, "rubble": 0.62, "encrusting": 0.75}

    # Colonies the size colonies are, against a vehicle 0.46 m long. On a
    # Caribbean fore reef most of what you swim past is between a fist and a
    # metre, with old boulder heads a good deal bigger.
    #
    # These are larger than the first pass, and deliberately: cover goes as
    # count times size squared, and a reef of 60% cover built from hand-sized
    # colonies needs seven million of them over a square kilometre. That is the
    # true number and it is not a number this pipeline can write to a text USD.
    # Colonies at their real size need about a third as many.
    sizes = {"branching": 0.95, "massive": 0.70, "table": 0.55,
             "brain": 0.62, "fan": 0.80, "finger": 0.60,
             "rubble": 0.30, "encrusting": 0.34}
    # A table two metres across is a table; the same multiplier on a plate that
    # is already three metres wide gives a seven metre sheet, and a handful of
    # those fill the view and read as scenery flats.
    per_kind = {"branching": 1.0, "rubble": 1.0, "encrusting": 0.36,
                "finger": 1.0, "massive": 0.9, "table": 0.55,
                "brain": 0.9, "fan": 1.0}

    kinds = sorted({kind for _, weights, _ in zonation.BANDS for kind in weights})
    variants = 6
    prototypes, colours = [], []
    for kind in kinds:
        for _ in range(variants):
            prototypes.append(
                coral.grow_one(kind, rng, sizes[kind] * rng.uniform(0.7, 1.4)))
            colours.append(coral.a_colour(rng, kind))

    footprint = np.zeros(len(prototypes))
    for i, (points, _) in enumerate(prototypes):
        if len(points):
            width = float(np.ptp(points[:, 0]))
            breadth = float(np.ptp(points[:, 1]))
            footprint[i] = (np.pi * (width / 2) * (breadth / 2)
                            * solidity[kinds[i // variants]])

    widths = np.array([max(1e-3, float(np.ptp(points[:, 0])))
                       for points, _ in prototypes])
    kind_scale = np.array([per_kind[k] for k in kinds])

    def a_draw(at_depth, rng):
        """Which prototype each colony is, how big, and what it covers."""
        _, which_kind, cap = zonation.community(at_depth, rng)
        which = which_kind * variants + rng.integers(0, variants, len(at_depth))
        scale = rng.uniform(0.65, 1.8, len(at_depth)) * kind_scale[which_kind]
        # No bigger than the band allows. A three metre table belongs on the
        # fore reef, not on a crest scoured to the rock every winter.
        scale = np.minimum(scale, cap / widths[which])
        return which, scale, footprint[which] * scale ** 2

    # How many colonies that cover needs.
    #
    # Measured from a trial draw rather than predicted from average sizes,
    # because the average is not what gets planted: kinds are drawn per depth
    # band and then capped, and the two together moved the real figure by a
    # factor of three. Predicting it is how the same reef came out at 48%, 67%
    # and 99% cover on three consecutive builds without anybody meaning it to.
    # Colonies are scattered, not tiled, so some of them land on each other.
    # Area A of colonies dropped at random over ground G covers 1 - exp(-A/G)
    # of it, not A/G — to cover half the ground you need seven tenths of it in
    # colonies, and to cover nine tenths you need more than twice. Planting the
    # naive area and measuring afterwards loses about two fifths of the cover,
    # every time, which is what it did.
    wanted_area = float((-np.log1p(-want) * step_x * step_y).sum())
    trial_rows, trial_columns = np.unravel_index(
        rng.choice(want.size, size=20000, p=(want / want.sum()).ravel()),
        want.shape)
    each_covers = float(a_draw(depth[trial_rows, trial_columns],
                               np.random.default_rng(seed + 1))[2].mean())
    needed = wanted_area / max(each_covers, 1e-6)
    how_many = int(min(how_many, max(1000, needed)))

    # In stands, not sprinkled.
    #
    # Coral recruits next to coral: a colony breaks, the fragment lands beside
    # it and grows, and the reef builds outward from what is already there. So
    # places are chosen for a thicket and colonies are dropped around each one,
    # which is what makes cover continuous where it is present rather than thin
    # everywhere — the failure mode that reads as ornaments on a beach.
    per_stand = 8
    stands = max(1, how_many // per_stand)
    flat = (want / want.sum()).ravel()
    picked = rng.choice(flat.size, size=stands, p=flat)
    stand_row, stand_column = np.unravel_index(picked, want.shape)
    centre_x = -across / 2 + stand_column * step_x
    centre_y = -across / 2 + stand_row * step_y

    belongs = np.repeat(np.arange(stands), per_stand)[:how_many]
    if belongs.size < how_many:
        belongs = np.concatenate(
            [belongs, rng.integers(0, stands, how_many - belongs.size)])

    # How wide a stand is: as wide as its colonies need in order to reach the
    # cover that ground was asked for, and no wider.
    #
    # A fixed couple of metres was fine while colonies were hand-sized and
    # became nonsense when they were grown to full size — twenty-two colonies a
    # metre across inside a two metre circle is ten of them in the same place.
    # It measured as ninety per cent cover over a fifth of the site, which is
    # both numbers being wrong in opposite directions at once.
    here = np.clip(want[stand_row, stand_column], 0.04, 0.94)
    reach = np.sqrt(per_stand * each_covers / (np.pi * here)) * 0.62
    spread = rng.normal(0, 1.0, (how_many, 2)) * reach[belongs][:, None]
    x = np.clip(centre_x[belongs] + spread[:, 0], -across / 2, across / 2)
    y = np.clip(centre_y[belongs] + spread[:, 1], -across / 2, across / 2)

    # Sat on the seabed under wherever it actually landed, not under the middle
    # of its stand — a colony two metres away can be half a metre lower.
    column = np.clip(((x + across / 2) / step_x).astype(int), 0, columns - 1)
    row = np.clip(((y + across / 2) / step_y).astype(int), 0, rows - 1)
    z = height[row, column] - 0.04   # bedded in, not balanced on top

    # What shape each one is, decided by the depth it landed at rather than by
    # one mix for the whole site.
    which, scale, covered_by = a_draw(depth[row, column], rng)
    which_kind = which // variants
    turn = rng.uniform(0, 2 * math.pi, how_many)

    (where / "coral.usda").write_text(
        _instancer(prototypes, colours, x, y, z, which, scale, turn))

    # How much of the ground this actually covers, square metre by square metre.
    #
    # A single number over "the reef" is not a measurement, because it depends
    # entirely on how generously the reef is defined — a loose threshold makes a
    # dense reef look thin and a tight one saturates at a hundred per cent
    # whatever the count is. Both happened. What a diver means by cover is
    # local: stand somewhere on the reef, look down, and see how much of the
    # ground is coral.
    metres = np.floor_divide(
        np.stack([x + across / 2, y + across / 2], axis=-1), 1.0).astype(int)
    metres = np.clip(metres, 0, int(across) - 1)
    per_metre = np.zeros((int(across), int(across)))
    np.add.at(per_metre, (metres[:, 1], metres[:, 0]), covered_by)

    lived_in = per_metre[per_metre > 0.02]
    cover = float(np.clip(np.median(lived_in), 0, 1)) if lived_in.size else 0.0
    thick = float((per_metre > 0.45).sum())

    asked_for = float(np.average(want, weights=want > 0.02)) if (want > 0.02).any() else 0.0
    return {"colonies": int(how_many), "prototypes": len(prototypes),
            "coverAskedFor": round(asked_for, 3),
            "points": int(sum(len(p) for p, _ in prototypes)),
            "coverWhereItGrows": round(cover, 3),
            "reefAreaM2": int(lived_in.size),
            "denseAreaM2": int(thick)}


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
