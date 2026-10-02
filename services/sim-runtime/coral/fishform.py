"""What a fish is shaped like, by body plan.

Grown rather than fetched, because nobody publishes CC0 scans of Caribbean reef
fish the way the Smithsonian publishes its corals. So these are built from the
three body plans that matter at the distance a vehicle sees them, and the
reasoning for each is written down rather than tuned until it looked right.

At three metres through this water a fish is a silhouette and a colour. What
carries the silhouette is the outline, the tail, and how deep the body is
compared to how long it is — which is exactly what separates a parrotfish from
a butterflyfish from a barracuda, and is why those are the three plans.

Every body is one metre nose to tail, facing +x, with its back up +z. The
runtime scales each to the length its species group is and turns it to face
where it is going.
"""

from __future__ import annotations

import numpy as np

# How deep a body is compared to how long, and how much it is flattened side to
# side. A fish is not a cylinder: almost all of them are taller than they are
# wide, and a deep-bodied one is a plate.
PLANS = {
    # Parrotfish, snapper, jack, grouper. A swimming shape.
    "fusiform": dict(deep=0.30, wide=0.16, tail=0.34, fin=0.13, nose=0.10),
    # Butterflyfish, angelfish, surgeonfish, damselfish. A plate on edge, and
    # from the side it is nearly a disc.
    "deep": dict(deep=0.52, wide=0.13, tail=0.26, fin=0.24, nose=0.06),
    # Wrasse, trumpetfish, barracuda. Long and thin, and the tail is small
    # because the whole body does the swimming.
    "elongate": dict(deep=0.15, wide=0.10, tail=0.20, fin=0.06, nose=0.14),
}

# Which plan each behaviour group swims under.
OF_GROUP = {
    "parrotfish": "fusiform", "snapper": "fusiform", "jack": "fusiform",
    "solitary": "fusiform",
    "surgeonfish": "deep", "damselfish": "deep", "butterflyfish": "deep",
    "wrasse": "elongate", "bottom": "elongate",
}

# Roughly what each group is, in the water, at the depth this reef is at.
#
# From the common names in the place's own record — Stoplight Parrotfish, Blue
# Tang, Yellowtail Snapper, Blue Chromis — and darkened, because a fish
# photographed under a strobe is not the colour of a fish at eight metres. They
# are a range because a school is not one colour.
COLOURS = {
    "parrotfish": ((0.10, 0.28, 0.24), (0.22, 0.40, 0.30)),
    "snapper": ((0.34, 0.31, 0.22), (0.52, 0.46, 0.30)),
    "surgeonfish": ((0.10, 0.16, 0.30), (0.16, 0.24, 0.42)),
    "damselfish": ((0.10, 0.20, 0.36), (0.18, 0.30, 0.48)),
    "wrasse": ((0.22, 0.34, 0.34), (0.38, 0.46, 0.40)),
    "butterflyfish": ((0.46, 0.42, 0.24), (0.62, 0.56, 0.32)),
    "jack": ((0.32, 0.36, 0.38), (0.48, 0.52, 0.54)),
    "solitary": ((0.26, 0.26, 0.22), (0.40, 0.38, 0.30)),
    # A fish that sits on the bottom is the colour of the bottom. That is what
    # sitting on the bottom is for.
    "bottom": ((0.20, 0.19, 0.15), (0.34, 0.31, 0.24)),
}

AROUND = 16      # sides to the body
ALONG = 22       # rings from nose to tail

# A tank's fish, which are not a reef's: chromis, wrasse, butterflies and gobies
# as an aquarium shows them, under white light at arm's length. Each is a back,
# a belly and an accent, because almost every fish is darker above than below
# (countershading) and that gradient is most of what makes one look like a fish
# rather than a painted toy.
TANK_COLOURS = {
    "damselfish": ((0.05, 0.32, 0.55), (0.55, 0.85, 0.88), (0.10, 0.55, 0.70)),     # blue-green chromis
    "wrasse": ((0.10, 0.45, 0.30), (0.85, 0.80, 0.55), (0.85, 0.30, 0.55)),         # green back, pink stripe
    "butterflyfish": ((0.95, 0.80, 0.10), (0.98, 0.96, 0.85), (0.05, 0.05, 0.06)),  # yellow, black eye band
    "bottom": ((0.45, 0.38, 0.30), (0.85, 0.80, 0.70), (0.90, 0.45, 0.15)),         # goby: sand with orange spots
    "surgeonfish": ((0.05, 0.15, 0.55), (0.30, 0.45, 0.80), (0.95, 0.85, 0.10)),    # blue tang, yellow tail
    "parrotfish": ((0.10, 0.50, 0.45), (0.60, 0.80, 0.70), (0.90, 0.40, 0.60)),
    "snapper": ((0.55, 0.45, 0.30), (0.90, 0.85, 0.75), (0.95, 0.85, 0.20)),
    "jack": ((0.35, 0.42, 0.48), (0.85, 0.88, 0.90), (0.20, 0.30, 0.40)),
    "solitary": ((0.35, 0.32, 0.25), (0.80, 0.75, 0.65), (0.50, 0.30, 0.20)),
}

# How many shapes a swimming stroke is drawn as. A body that never bends glides
# like a toy on a wire; eight bent shapes cycled at the tail-beat rate is a
# fish swimming, at no cost a renderer notices.
STROKE = 8


def body(plan: str, bend: float = 0.0):
    """One fish, a metre long, facing +x.

    A tube of elliptical rings whose height and width follow the outline, then
    a caudal fin and a dorsal fin as flat triangles. Flat fins on purpose: a
    fin is a membrane a fraction of a millimetre thick, and a fish rendered
    with a solid wedge for a tail reads as a toy.
    """
    says = PLANS[plan]
    points, faces = [], []

    # The outline, nose to tail root. A quarter ellipse into the shoulder and
    # a taper out of it, which is what a fish looks like from above and from
    # the side.
    xs = np.linspace(0.0, 1.0 - says["tail"], ALONG)
    # The nose is at +x. It was at -x, and `facing` turns +x down the way a
    # fish is going, so every fish on this platform swam tail first.
    def sway(along):
        # A carangiform stroke: the front holds still and the back half
        # swings, more towards the tail, as a travelling wave.
        s = np.clip(along, 0.0, 1.0)
        return 0.11 * bend * s ** 2 * np.sin(np.pi * 1.4 * s)
    shoulder = says["nose"] + 0.18
    fat = np.where(
        xs < shoulder,
        np.sqrt(np.maximum(0.0, 1.0 - ((shoulder - xs) / max(shoulder, 1e-6)) ** 2)),
        (1.0 - (xs - shoulder) / max(1.0 - says["tail"] - shoulder, 1e-6)) ** 0.7)
    fat = np.clip(fat, 0.06, 1.0)

    turn = np.linspace(0, 2 * np.pi, AROUND, endpoint=False)
    for i, x in enumerate(xs):
        for a in turn:
            points.append((0.5 - x,
                           says["wide"] * fat[i] * np.sin(a) + sway(x),
                           says["deep"] * fat[i] * np.cos(a)))
    for i in range(ALONG - 1):
        for j in range(AROUND):
            k = (j + 1) % AROUND
            a = i * AROUND + j
            b = i * AROUND + k
            c = (i + 1) * AROUND + j
            d = (i + 1) * AROUND + k
            faces.append((a, c, b))
            faces.append((b, c, d))

    # The tail. Two lobes off the tail root, which is the shape that reads as
    # a fish from behind as well as from the side.
    root = 0.5 - xs[-1]
    tip = -0.5
    span = says["fin"] * 1.9
    flick = sway(1.0) + 0.06 * bend          # the tail is where the stroke ends
    at = len(points)
    points += [(root, sway(xs[-1]), 0.0), (tip, flick, span), (tip, flick, -span),
               (tip + 0.05, flick * 0.9, 0.18 * span)]
    faces += [(at, at + 1, at + 3), (at, at + 3, at + 2)]

    # And a dorsal fin, along the back.
    at = len(points)
    mid = len(xs) // 2
    points += [(0.5 - xs[3], sway(xs[3]), says["deep"] * fat[3]),
               (0.5 - xs[-3], sway(xs[-3]), says["deep"] * fat[-3]),
               (0.5 - xs[mid], sway(xs[mid]), says["deep"] * fat[mid] + says["fin"])]
    faces += [(at, at + 2, at + 1)]

    return np.array(points, dtype="float32"), np.array(faces, dtype="int32")


def painted(points, group: str, rng) -> np.ndarray:
    """A colour per vertex: dark back, pale belly, and the group's accent where
    it sits on that fish — a band through the eye, a stripe, spots, a tail."""
    back, belly, accent = TANK_COLOURS.get(group, TANK_COLOURS["solitary"])
    back, belly, accent = (np.array(c) * rng.uniform(0.9, 1.1) for c in (back, belly, accent))
    z = points[:, 2]
    up = np.clip((z - z.min()) / max(1e-6, z.max() - z.min()), 0.0, 1.0)[:, None]
    colour = belly + (back - belly) * up ** 0.8
    along = 0.5 - points[:, 0]                       # 0 at the nose, 1 at the tail
    mark = np.zeros(len(points), dtype=bool)
    if group == "butterflyfish":
        mark = (along > 0.12) & (along < 0.2)
    elif group == "wrasse":
        mark = np.abs(z - 0.0) < 0.025
    elif group == "bottom":
        mark = (np.sin(along * 60.0) * np.sin(z * 90.0)) > 0.75
    elif group == "surgeonfish":
        mark = along > 0.82
    elif group == "damselfish":
        mark = along > 0.8
    colour[mark] = accent
    # And an eye, which is the first thing anybody looks for on a fish.
    eye = (along < 0.1) & (along > 0.05) & (z > 0.02) & (np.abs(points[:, 1]) > 0.01)
    colour[eye] = (0.02, 0.02, 0.02)
    return np.clip(colour, 0.0, 1.0)


def a_colour(group: str, rng) -> tuple:
    """One fish's colour, from the range its group covers."""
    low, high = COLOURS.get(group, COLOURS["solitary"])
    return tuple(float(rng.uniform(a, b)) for a, b in zip(low, high))


def facing(going) -> tuple:
    """A quaternion that points a body down the way it is swimming.

    Yaw and pitch only. A fish does roll, and a fish that rolls in a flocking
    model rolls because the arithmetic wobbled rather than because it turned,
    which reads as a dying fish rather than a swimming one.
    """
    x, y, z = (float(v) for v in going)
    flat = np.hypot(x, y)
    if flat < 1e-9 and abs(z) < 1e-9:
        return (1.0, 0.0, 0.0, 0.0)
    yaw = np.arctan2(y, x)
    pitch = np.arctan2(z, max(flat, 1e-9))
    cy, sy = np.cos(yaw / 2), np.sin(yaw / 2)
    cp, sp = np.cos(-pitch / 2), np.sin(-pitch / 2)
    # Yaw about z, then pitch about y.
    return (float(cy * cp), float(-sy * sp), float(cy * sp), float(sy * cp))
