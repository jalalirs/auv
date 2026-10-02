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

AROUND = 20      # sides to the body
ALONG = 30       # rings from nose to tail

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
    """One fish, a metre long, nose at +x. See `anatomy`."""
    points, faces, _ = anatomy(plan, bend)
    return points, faces


def anatomy(plan: str, bend: float = 0.0):
    """One fish, a metre long, nose at +x, and which part each vertex is.

    A body of elliptical rings whose height and width follow the outline; a
    forked tail; a dorsal fin along the back and an anal fin under it; two
    pectoral fins behind the gills; and two eyes. Fins are membranes, so they
    are thin surfaces drawn from both sides. Parts: 0 body, 1 fin, 2 eye.
    """
    says = PLANS[plan]
    points, faces, parts = [], [], []

    def add(pts, fcs, part):
        at = len(points)
        points.extend(pts)
        faces.extend([tuple(at + i for i in f) for f in fcs])
        parts.extend([part] * len(pts))

    xs = np.linspace(0.0, 1.0 - says["tail"], ALONG)
    shoulder = says["nose"] + 0.18
    fat = np.where(
        xs < shoulder,
        np.sqrt(np.maximum(0.0, 1.0 - ((shoulder - xs) / max(shoulder, 1e-6)) ** 2)),
        (1.0 - (xs - shoulder) / max(1.0 - says["tail"] - shoulder, 1e-6)) ** 0.7)
    fat = np.clip(fat, 0.05, 1.0)

    # The nose is at +x. It was at -x, and `facing` turns +x down the way a
    # fish is going, so every fish on this platform swam tail first.
    def sway(along):
        # A carangiform stroke: the front holds still and the back half
        # swings, more towards the tail, as a travelling wave.
        s = np.clip(along, 0.0, 1.0)
        return 0.11 * bend * s ** 2 * np.sin(np.pi * 1.4 * s)

    turn = np.linspace(0, 2 * np.pi, AROUND, endpoint=False)
    ring = []
    for i, x in enumerate(xs):
        for a in turn:
            ring.append((0.5 - x, says["wide"] * fat[i] * np.sin(a) + sway(x), says["deep"] * fat[i] * np.cos(a)))
    tube = []
    for i in range(ALONG - 1):
        for j in range(AROUND):
            k = (j + 1) % AROUND
            a, b = i * AROUND + j, i * AROUND + k
            c, d = (i + 1) * AROUND + j, (i + 1) * AROUND + k
            tube += [(a, c, b), (b, c, d)]
    # Close the snout.
    ring.append((0.5, 0.0, 0.0))
    tube += [(len(ring) - 1, j, (j + 1) % AROUND) for j in range(AROUND)]
    add(ring, tube, 0)

    def at_body(along, up):
        """A point on the back (up=1) or belly (up=-1) at a station."""
        i = int(np.clip(along / (1.0 - says["tail"]) * (ALONG - 1), 0, ALONG - 1))
        return (0.5 - xs[i], sway(xs[i]), up * says["deep"] * fat[i])

    # A forked tail: two lobes and a notch between them.
    root = 1.0 - says["tail"]
    span = says["fin"] * 2.1
    flick = sway(1.0) + 0.07 * bend
    tip = -0.5
    peduncle = says["deep"] * fat[-1]
    add([(0.5 - root, sway(root), peduncle), (0.5 - root, sway(root), -peduncle),
         (tip, flick, span), (tip + 0.13, flick * 0.85, 0.0), (tip, flick, -span)],
        [(0, 2, 3), (1, 3, 4), (0, 3, 1)], 1)
    # A dorsal fin along the back, high in front and sloping away.
    fin = []
    stations = np.linspace(0.22, 0.72, 7)
    for n, along in enumerate(stations):
        base = at_body(along, 1)
        lift = says["fin"] * (1.0 - 0.6 * n / (len(stations) - 1))
        fin += [base, (base[0] - 0.03, base[1], base[2] + lift)]
    add(fin, [(2 * n, 2 * n + 2, 2 * n + 1) for n in range(len(stations) - 1)]
        + [(2 * n + 1, 2 * n + 2, 2 * n + 3) for n in range(len(stations) - 1)], 1)
    # An anal fin under the back half.
    fin = []
    stations = np.linspace(0.5, 0.74, 4)
    for along in stations:
        base = at_body(along, -1)
        fin += [base, (base[0] - 0.04, base[1], base[2] - says["fin"] * 0.7)]
    add(fin, [(2 * n, 2 * n + 1, 2 * n + 2) for n in range(len(stations) - 1)]
        + [(2 * n + 1, 2 * n + 3, 2 * n + 2) for n in range(len(stations) - 1)], 1)
    # Pectoral fins behind the gills, swept back and a little down.
    i = int(0.24 / (1.0 - says["tail"]) * (ALONG - 1))
    for side in (1.0, -1.0):
        y = side * says["wide"] * fat[i]
        add([(0.5 - xs[i], y, 0.0), (0.5 - xs[i] - 0.03, y, -0.05 * says["deep"] / 0.3),
             (0.5 - xs[i] - 0.16, y + side * 0.06, -0.02)], [(0, 1, 2)], 1)
    # And the eyes: a dark ball each side of the head.
    i = int(0.09 / (1.0 - says["tail"]) * (ALONG - 1))
    r = 0.035
    for side in (1.0, -1.0):
        centre = np.array([0.5 - xs[i], side * says["wide"] * fat[i] * 0.85, says["deep"] * fat[i] * 0.3])
        ball, cells = [], []
        for a in range(7):
            for b in range(10):
                th, ph = np.pi * a / 6, 2 * np.pi * b / 10
                ball.append(tuple(centre + r * np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)])))
        for a in range(6):
            for b in range(10):
                q, w = a * 10 + b, a * 10 + (b + 1) % 10
                cells += [(q, q + 10, w), (w, q + 10, w + 10)]
        add(ball, cells, 2)

    return (np.array(points, dtype="float32"), np.array(faces, dtype="int32"),
            np.array(parts, dtype="int8"))


def _sheets():
    try:
        from coral import fish_species
    except ImportError:          # the runtime puts coral/ itself on the path
        import fish_species
    return fish_species.SPECIES


def plan_of(kind: str) -> str:
    """The body plan a species or a behaviour group swims under."""
    sheets = _sheets()
    if kind in sheets:
        return sheets[kind]["plan"]
    return OF_GROUP[kind]


def marked(points, mark: str, plan: str) -> tuple[np.ndarray, np.ndarray]:
    """Where a species' marks are on the body: (accent, edge) masks.

    The marks that name a reef fish at a glance — a clownfish's three white
    bands, a copperband's bars, a foureye's false eye by its tail, a wrasse's
    stripes, a tang's tail. `edge` is a thin dark rim, which bands and
    eyespots have."""
    x, z = points[:, 0], points[:, 2]
    along = 0.5 - x                                  # 0 at the nose, 1 at the tail
    height = np.clip((z - z.min()) / max(1e-6, z.max() - z.min()), 0.0, 1.0)
    accent = np.zeros(len(points), dtype=bool)
    edge = np.zeros(len(points), dtype=bool)
    if mark == "bands":
        for a, b in ((0.17, 0.25), (0.45, 0.53), (0.80, 0.86)):
            accent |= (along > a) & (along < b)
            edge |= ((along > a - 0.015) & (along <= a)) | ((along >= b) & (along < b + 0.015))
    elif mark == "stripes":
        if plan == "elongate":
            accent = (np.abs((height * 6.0) % 1.0 - 0.5) < 0.13) & (along < 0.85)
        else:
            accent = np.abs(height - 0.5) < 0.07
            accent |= along > 0.84
    elif mark == "bars":
        accent = (np.sin(along * 2.0 * np.pi * 3.0) > 0.55) & (along > 0.1) & (along < 0.85)
    elif mark == "tail":
        accent = along > 0.82
    elif mark == "eyespot":
        ring = (along - 0.72) ** 2 + ((height - 0.62) * 0.6) ** 2
        accent = ring < 0.045 ** 2
        edge = (ring >= 0.045 ** 2) & (ring < 0.06 ** 2)
    elif mark == "spots":
        accent = (np.sin(along * 60.0) * np.sin(z * 90.0)) > 0.75
    return accent, edge


def painted(points, group: str, rng, parts=None) -> np.ndarray:
    """A colour per vertex: dark back, pale belly, and the accent where it sits
    on that fish — bands, stripes, bars, an eyespot, spots, a tail. A species
    is painted from its own sheet; a behaviour group from the group's."""
    sheets = _sheets()
    if group in sheets:
        sheet = sheets[group]
        back, belly, accent = (np.array(c) * rng.uniform(0.95, 1.05) for c in sheet["palette"])
        colour = _shaded(points, back, belly)
        marks, rim = marked(points, sheet["mark"], sheet["plan"])
        colour[marks] = accent
        colour[rim] = (0.03, 0.03, 0.035)
        return _finished(colour, accent, parts)
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
    return _finished(colour, accent, parts)


def _shaded(points, back, belly) -> np.ndarray:
    z = points[:, 2]
    up = np.clip((z - z.min()) / max(1e-6, z.max() - z.min()), 0.0, 1.0)[:, None]
    return belly + (back - belly) * up ** 0.8


def _finished(colour, accent, parts) -> np.ndarray:
    if parts is not None:
        # Fins carry the body's colour lightened towards the accent, and the
        # eye is a dark ball with nothing painted on it.
        fins = parts == 1
        colour[fins] = 0.5 * colour[fins] + 0.5 * np.asarray(accent)
        colour[parts == 2] = (0.015, 0.015, 0.02)
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
