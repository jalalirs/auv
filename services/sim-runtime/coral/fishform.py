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

AROUND = 8       # sides to the body
ALONG = 11       # rings from nose to tail


def body(plan: str):
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
    shoulder = says["nose"] + 0.18
    fat = np.where(
        xs < shoulder,
        np.sqrt(np.maximum(0.0, 1.0 - ((shoulder - xs) / max(shoulder, 1e-6)) ** 2)),
        (1.0 - (xs - shoulder) / max(1.0 - says["tail"] - shoulder, 1e-6)) ** 0.7)
    fat = np.clip(fat, 0.06, 1.0)

    turn = np.linspace(0, 2 * np.pi, AROUND, endpoint=False)
    for i, x in enumerate(xs):
        for a in turn:
            points.append((x - 0.5,
                           says["wide"] * fat[i] * np.sin(a),
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
    root = xs[-1] - 0.5
    tip = 0.5
    span = says["fin"] * 1.9
    at = len(points)
    points += [(root, 0.0, 0.0), (tip, 0.0, span), (tip, 0.0, -span),
               (tip, 0.0, 0.18 * span)]
    faces += [(at, at + 1, at + 3), (at, at + 3, at + 2)]

    # And a dorsal fin, along the back.
    at = len(points)
    points += [(xs[2] - 0.5, 0.0, says["deep"] * fat[2]),
               (xs[-2] - 0.5, 0.0, says["deep"] * fat[-2]),
               (xs[len(xs) // 2] - 0.5, 0.0,
                says["deep"] * fat[len(xs) // 2] + says["fin"])]
    faces += [(at, at + 2, at + 1)]

    return np.array(points, dtype="float32"), np.array(faces, dtype="int32")


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
