"""Growing coral.

Real coral scans exist and are genuinely CC0 — the Smithsonian has about ninety
of them — but every route to the bytes needs an account, and a reef needs
thousands of colonies rather than ninety. So these are grown instead.

Which is not a compromise. Coral morphology is one of the most studied growth
processes there is, and the shapes come from a handful of rules: branching
colonies extend at their tips and split at a species-typical angle; tables grow
outward faster than upward once they reach light; massive corals accrete more or
less evenly and end up as boulders; brain corals fold their surface to get more
of it. Growing them from those rules gives a reef where every colony is
different, which is the thing a library of ninety scans cannot do however good
each one is.

Everything here is metres, Z up, and sitting on z=0 so a colony can be dropped
straight onto a seabed.
"""

from __future__ import annotations

import math

import numpy as np

# What lives on a reef, and how much of it. Roughly the composition of a
# sheltered Indo-Pacific fore-reef: mostly branching and massive, tables where
# there is light and room, and soft corals filling in.
COMMUNITY = (
    ("branching", 0.34),   # the signature of a reef, and what you see first
    ("rubble", 0.22),      # broken coral and stone: the floor of a real one
    ("finger", 0.14),
    ("massive", 0.11),
    ("encrusting", 0.07),  # sheets over the rock; too many read as litter
    ("table", 0.06),
    ("brain", 0.04),
    ("fan", 0.02),
)

# Colours corals actually are. The browns and tans are zooxanthellae, which is
# what most healthy coral looks like from a metre away; the pinks, purples and
# yellows are pigments that show in shallow water. A reef of uniformly bright
# colours is an aquarium poster, and a reef of uniform brown is a dead one.
# What a reef is actually coloured.
#
# Overwhelmingly browns, tans and olives — that is zooxanthellae, the algae
# living in the coral, and it is what nearly every healthy colony looks like
# from a metre away. The pinks, purples and yellows are real and are the
# minority: they are pigments that show in shallow, bright water, and a reef
# where they are as common as brown is an aquarium poster.
#
# Saturated for the ones that are coloured, because everything down here is lit
# by blue-green water and seen through more of it, and both wash colour out — a
# palette that looks right in a swatch comes back pastel.
PALETTE = (
    ((0.44, 0.31, 0.16), 0.20),   # dark brown
    ((0.58, 0.41, 0.20), 0.20),   # brown
    ((0.70, 0.53, 0.28), 0.16),   # tan
    ((0.46, 0.46, 0.26), 0.12),   # olive
    ((0.78, 0.62, 0.30), 0.09),   # gold
    ((0.80, 0.36, 0.34), 0.06),   # pink
    ((0.86, 0.62, 0.18), 0.06),   # yellow
    ((0.52, 0.24, 0.50), 0.05),   # purple
    ((0.88, 0.44, 0.16), 0.04),   # orange
    ((0.30, 0.48, 0.52), 0.02),   # blue-grey
)


def a_colour(rng, kind: str | None = None):
    """One colour, drawn the way a reef is coloured rather than evenly.

    And by species, because colour is not spread evenly across a reef: the
    pinks and purples anybody photographs are nearly all branching Acropora and
    Pocillopora tips, while the boulders and the rubble are brown. A palette
    applied uniformly gives pink boulders and brown staghorn, which is exactly
    backwards and reads as a toybox.
    """
    colours = [c for c, _ in PALETTE]
    weights = np.array([w for _, w in PALETTE], dtype=float)
    if kind in ("branching", "table", "fan"):
        # Shift toward the coloured end for the ones that are coloured.
        weights = weights * np.array([0.4, 0.5, 0.7, 0.7, 1.0,
                                      2.6, 2.2, 2.4, 2.0, 1.2])
    elif kind in ("rubble", "encrusting"):
        # And hard toward brown for the ones that are the reef's fabric.
        weights = weights * np.array([2.2, 2.2, 1.8, 1.4, 0.6,
                                      0.15, 0.2, 0.1, 0.1, 0.3])
    weights = weights / weights.sum()
    return colours[int(rng.choice(len(colours), p=weights))]


def roughen(points, by, rng, scale=2.4):
    """Push every vertex about a bit, so nothing is a smooth primitive.

    Coral is rough at every scale — corallites, ridges, the scars of old growth
    — and a smooth dome reads as an egg however well it is shaded. This is not a
    model of any of that; it is enough high-frequency variation that the eye
    stops seeing a primitive.
    """
    if len(points) == 0:
        return points
    phase = rng.uniform(0, 6.283, 3)
    wobble = (np.sin(points[:, 0] * scale + phase[0])
              * np.sin(points[:, 1] * scale * 1.3 + phase[1])
              * np.sin(points[:, 2] * scale * 0.9 + phase[2]))
    radial = points - points.mean(axis=0)
    length = np.linalg.norm(radial, axis=1, keepdims=True)
    length[length < 1e-9] = 1.0
    return points + (radial / length) * (wobble[:, None] * by)


def _cylinder(a, b, radius_a, radius_b, sides=6):
    """A tapered tube from a to b. The unit every branch is made of."""
    axis = b - a
    length = np.linalg.norm(axis)
    if length < 1e-6:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    axis = axis / length

    # Any two directions across the axis.
    other = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, other)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)

    angles = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    ring = np.cos(angles)[:, None] * u + np.sin(angles)[:, None] * v
    points = np.vstack([a + ring * radius_a, b + ring * radius_b])

    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append([i, j, sides + i])
        faces.append([j, sides + j, sides + i])
    return points, np.array(faces, dtype=int)


def _join(pieces):
    points, faces, at = [], [], 0
    for p, f in pieces:
        if len(p) == 0:
            continue
        points.append(p)
        faces.append(f + at)
        at += len(p)
    if not points:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    return np.vstack(points), np.vstack(faces)


def branching(rng, height=0.8):
    """Acropora — the staghorn kind. Tips extend, and split as they go.

    The angle between daughter branches is the most species-typical thing about
    a coral, which is why these read as coral rather than as trees: about forty
    degrees, and tightening as the branches thin.
    """
    pieces = []
    thickness = height * 0.085

    def grow(base, direction, length, radius, depth):
        if depth > 5 or length < 0.015 or radius < 0.003:
            return
        # A branch does not go straight. It wanders towards the light, which is
        # up, and the wander is what stops a colony looking manufactured.
        direction = direction + rng.normal(0, 0.22, 3) + np.array([0, 0, 0.30])
        direction /= np.linalg.norm(direction)
        tip = base + direction * length
        pieces.append(_cylinder(base, tip, radius, radius * 0.72))

        # Three at the base, two after — a staghorn colony is mostly tips, and
        # two-way splitting all the way up gives a sparse candelabra rather
        # than the dense thicket the thing actually is.
        children = 3 if depth < 2 else (2 if depth < 4 else int(rng.integers(2, 4)))
        for _ in range(int(children)):
            spread = math.radians(rng.uniform(28, 52))
            axis = np.cross(direction, rng.normal(0, 1, 3))
            if np.linalg.norm(axis) < 1e-6:
                continue
            axis /= np.linalg.norm(axis)
            # Rodrigues, to tilt the child off its parent by the spread angle.
            child = (direction * math.cos(spread)
                     + np.cross(axis, direction) * math.sin(spread)
                     + axis * np.dot(axis, direction) * (1 - math.cos(spread)))
            grow(tip, child, length * rng.uniform(0.62, 0.80),
                 radius * rng.uniform(0.70, 0.84), depth + 1)

    grow(np.zeros(3), np.array([0.0, 0.0, 1.0]), height * 0.30, thickness, 0)
    return _join(pieces)


def finger(rng, height=0.5):
    """Porites — fat blunt fingers off a common base, barely branching."""
    pieces = []
    for _ in range(int(rng.integers(5, 11))):
        lean = rng.normal(0, 0.30, 3)
        lean[2] = abs(lean[2]) + 1.4
        lean /= np.linalg.norm(lean)
        base = np.array([rng.normal(0, height * 0.14), rng.normal(0, height * 0.14), 0.0])
        length = height * rng.uniform(0.55, 1.0)
        radius = height * rng.uniform(0.10, 0.16)
        tip = base + lean * length
        pieces.append(_cylinder(base, tip, radius, radius * 0.85, sides=7))
        # A blunt cap, because Porites fingers end in a dome and not a point.
        pieces.append(_dome(tip, radius * 0.85, radius * 0.7, rows=3, sides=7))
    return _join(pieces)


def _dome(centre, radius, height, rows=5, sides=10, squash=1.0, wobble=None, rng=None):
    """Half an ellipsoid. Massive corals are this, roughened."""
    points = [centre + np.array([0, 0, height])]
    for r in range(1, rows + 1):
        polar = (r / rows) * (math.pi / 2)
        ring_r, ring_z = math.sin(polar), math.cos(polar)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            p = centre + np.array([ring_r * radius * math.cos(a),
                                   ring_r * radius * math.sin(a),
                                   ring_z * height * squash])
            if wobble and rng is not None:
                p += rng.normal(0, wobble, 3)
            points.append(p)
    points = np.array(points)

    faces = []
    for s in range(sides):
        faces.append([0, 1 + s, 1 + (s + 1) % sides])
    for r in range(rows - 1):
        base, nxt = 1 + r * sides, 1 + (r + 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([base + s, nxt + s, base + t])
            faces.append([base + t, nxt + s, nxt + t])
    return points, np.array(faces, dtype=int)


def massive(rng, height=0.7):
    """A boulder coral. Accretes evenly, ends up lumpy rather than smooth."""
    return _dome(np.zeros(3), height * rng.uniform(0.55, 0.85), height,
                 rows=9, sides=20, squash=1.0,
                 wobble=height * 0.045, rng=rng)


def brain(rng, height=0.6):
    """A brain coral: a dome that folded its surface to get more of it."""
    radius = height * rng.uniform(0.8, 1.1)
    rows, sides = 11, 30
    points = [np.array([0, 0, height])]
    turns = rng.uniform(4.0, 7.0)
    for r in range(1, rows + 1):
        polar = (r / rows) * (math.pi / 2)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            # The grooves: a ripple that runs around the dome, which is what
            # gives a brain coral its meanders.
            groove = 0.028 * height * math.sin(turns * a + 5.0 * polar)
            rr = math.sin(polar) * radius + groove
            zz = math.cos(polar) * height + groove
            points.append(np.array([rr * math.cos(a), rr * math.sin(a), zz]))
    points = np.array(points)
    faces = []
    for s in range(sides):
        faces.append([0, 1 + s, 1 + (s + 1) % sides])
    for r in range(rows - 1):
        base, nxt = 1 + r * sides, 1 + (r + 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([base + s, nxt + s, base + t])
            faces.append([base + t, nxt + s, nxt + t])
    return points, np.array(faces, dtype=int)


def table(rng, height=0.5):
    """A table coral: a stem, and a plate that spread once it found light."""
    radius = height * rng.uniform(1.6, 2.6)
    stem = _cylinder(np.zeros(3), np.array([0, 0, height * 0.75]),
                     height * 0.13, height * 0.09, sides=8)

    sides, rings = 20, 4
    points, faces = [], []
    for r in range(rings + 1):
        share = r / rings
        for s in range(sides):
            a = 2 * math.pi * s / sides
            # Plates are not flat; they dish slightly and their edge undulates.
            lift = height * (0.75 + 0.10 * share ** 2) + 0.02 * math.sin(6 * a)
            rr = radius * share * (1.0 + 0.08 * math.sin(5 * a))
            points.append([rr * math.cos(a), rr * math.sin(a), lift])
    points = np.array(points)
    for r in range(rings):
        base, nxt = r * sides, (r + 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([base + s, nxt + s, base + t])
            faces.append([base + t, nxt + s, nxt + t])
    return _join([stem, (points, np.array(faces, dtype=int))])


def fan(rng, height=0.9):
    """A sea fan: branching in a plane, because it feeds on the current."""
    pieces = []
    thickness = height * 0.018

    def grow(base, direction, length, radius, depth):
        if depth > 5 or length < 0.015:
            return
        direction = direction + np.array([rng.normal(0, 0.05), 0.0, 0.16])
        direction /= np.linalg.norm(direction)
        tip = base + direction * length
        pieces.append(_cylinder(base, tip, radius, radius * 0.8, sides=4))
        for turn in (-1, 1):
            spread = math.radians(rng.uniform(22, 40)) * turn
            child = np.array([
                direction[0] * math.cos(spread) - direction[2] * math.sin(spread),
                direction[1] * 0.25,
                direction[0] * math.sin(spread) + direction[2] * math.cos(spread)])
            child /= np.linalg.norm(child)
            grow(tip, child, length * rng.uniform(0.68, 0.84),
                 radius * 0.82, depth + 1)

    grow(np.zeros(3), np.array([0.0, 0.0, 1.0]), height * 0.3, thickness, 0)
    return _join(pieces)


def rubble(rng, height=0.3):
    """Broken coral and stone.

    The thing that makes a reef a floor rather than a lawn of ornaments. Most of
    a real reef, by area, is the wreckage of the last one: fragments, old heads
    rolled and cemented, and sand between. Leave it out and every colony sits on
    clean sand like a chess piece, which is exactly what the first reefs looked
    like.
    """
    pieces = []
    for _ in range(int(rng.integers(2, 5))):
        where = np.array([rng.normal(0, height * 0.5), rng.normal(0, height * 0.5), 0.0])
        pieces.append(_dome(where, height * rng.uniform(0.5, 1.2),
                            height * rng.uniform(0.25, 0.55),
                            rows=3, sides=7, wobble=height * 0.16, rng=rng))
    return _join(pieces)


def encrusting(rng, height=0.25):
    """A sheet growing over the rock. Wide, low, and following what it is on."""
    radius = height * rng.uniform(2.0, 3.4)
    rows, sides = 3, 14
    points, faces = [], []
    for r in range(rows + 1):
        share = r / rows
        for s in range(sides):
            a = 2 * math.pi * s / sides
            lift = height * (1.0 - share ** 2) * rng.uniform(0.85, 1.15)
            rr = radius * share * (1.0 + 0.22 * math.sin(4 * a + rng.uniform(0, 1)))
            points.append([rr * math.cos(a), rr * math.sin(a), lift * 0.22])
    points = np.array(points)
    for r in range(rows):
        base, nxt = r * sides, (r + 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([base + s, nxt + s, base + t])
            faces.append([base + t, nxt + s, nxt + t])
    return points, np.array(faces, dtype=int)


GROWERS = {"branching": branching, "massive": massive, "table": table,
           "brain": brain, "fan": fan, "finger": finger,
           "rubble": rubble, "encrusting": encrusting}


def grow_one(kind: str, rng, size: float):
    """One colony, of a kind, about a size across."""
    points, faces = GROWERS[kind](rng, size)
    if len(points) == 0:
        return points, faces

    # Roughened by however much that kind is rough. A boulder coral is knobbly;
    # a table's plate is nearly flat and only its edge is ragged.
    by = {"massive": 0.055, "brain": 0.030, "table": 0.020,
          "branching": 0.014, "finger": 0.022, "fan": 0.008,
          "rubble": 0.070, "encrusting": 0.030}[kind] * size
    points = roughen(points, by, rng, scale=2.0 + 6.0 / max(size, 0.2))
    # Every colony is turned, so a field of them has no grain.
    turn = rng.uniform(0, 2 * math.pi)
    spin = np.array([[math.cos(turn), -math.sin(turn), 0],
                     [math.sin(turn), math.cos(turn), 0],
                     [0, 0, 1]])
    return points @ spin.T, faces
