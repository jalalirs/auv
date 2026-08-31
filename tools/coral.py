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
    ("branching", 0.34),
    ("massive", 0.22),
    ("table", 0.12),
    ("brain", 0.12),
    ("fan", 0.10),
    ("finger", 0.10),
)

# Colours corals actually are. The browns and tans are zooxanthellae, which is
# what most healthy coral looks like from a metre away; the pinks, purples and
# yellows are pigments that show in shallow water. A reef of uniformly bright
# colours is an aquarium poster, and a reef of uniform brown is a dead one.
PALETTE = (
    (0.71, 0.54, 0.35),   # tan
    (0.62, 0.44, 0.28),   # brown
    (0.80, 0.62, 0.42),   # pale gold
    (0.84, 0.49, 0.52),   # dusty pink
    (0.70, 0.42, 0.62),   # purple
    (0.86, 0.72, 0.38),   # yellow
    (0.52, 0.62, 0.50),   # olive green
    (0.90, 0.60, 0.36),   # orange
)


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
                 rows=6, sides=14, squash=1.0,
                 wobble=height * 0.045, rng=rng)


def brain(rng, height=0.6):
    """A brain coral: a dome that folded its surface to get more of it."""
    radius = height * rng.uniform(0.8, 1.1)
    rows, sides = 8, 22
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


GROWERS = {"branching": branching, "massive": massive, "table": table,
           "brain": brain, "fan": fan, "finger": finger}


def grow_one(kind: str, rng, size: float):
    """One colony, of a kind, about a size across."""
    points, faces = GROWERS[kind](rng, size)
    if len(points) == 0:
        return points, faces
    # Every colony is turned, so a field of them has no grain.
    turn = rng.uniform(0, 2 * math.pi)
    spin = np.array([[math.cos(turn), -math.sin(turn), 0],
                     [math.sin(turn), math.cos(turn), 0],
                     [0, 0, 1]])
    return points @ spin.T, faces
