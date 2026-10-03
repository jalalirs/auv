"""What a fish is shaped like: its body plan, and its own form and marks.

Grown rather than fetched, because nobody publishes CC0 scans of reef fish the
way the Smithsonian publishes its corals. So these are built from body plans,
and the reasoning for each is written down rather than tuned until it looked
right.

A plan is the silhouette class — a swimming spindle, a plate on edge, a long
thin wrasse, a shark, a batfish's disc of fins, a grouper, a ray. A species'
sheet (fish_species.py) may then give its own `form` — how deep, the nose and
forehead, which tail (forked, lunate, rounded, truncate, a shark's), which
dorsal (spiny, tall, a shark's two, a bannerfish's filament, low), how big the
anal and pectoral fins are — and its `marks`: what names it at a glance, read
off photographs of it (the Jeddah airport tank's, for the Red Sea's).

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
    # A requiem shark: a long spindle with a pointed snout, a tall triangular
    # first dorsal and a small second, big stiff pectorals, and a tail whose
    # upper lobe is twice the lower.
    "shark": dict(deep=0.16, wide=0.15, tail=0.27, fin=0.20, nose=0.14, snout=0.9, stalk=0.22,
                  tailshape="shark", dorsal="shark", anal=0.35, pectoral=2.4),
    # A batfish: a deep body under a dorsal and an anal fin each as tall as
    # the body, so that from the side it is a disc taller than it is long.
    "disc": dict(deep=0.50, wide=0.09, tail=0.17, fin=0.42, nose=0.05,
                 tailshape="truncate", dorsal="tall", anal=1.5, pectoral=0.7),
    # A grouper: heavy, wide-headed, a long low dorsal and a rounded tail.
    "grouper": dict(deep=0.29, wide=0.19, tail=0.22, fin=0.09, nose=0.13,
                    tailshape="rounded", dorsal="low", anal=0.8, pectoral=1.3),
    # A ray: a flat disc that flies on its wings, a head in front, a whip of a
    # tail behind. Built on its own (`ray`); a metre nose to tail like the rest.
    "ray": dict(deep=0.06, wide=0.42, tail=0.55, fin=0.0, nose=0.08, tailshape="whip"),
}

# What a form is when its sheet says nothing about a part.
FORM_DEFAULTS = dict(tailshape="forked", dorsal="spiny", anal=0.7, pectoral=1.0, hump=0.0)

# Which plan each behaviour group swims under.
OF_GROUP = {
    "parrotfish": "fusiform", "snapper": "fusiform", "jack": "fusiform",
    "solitary": "fusiform",
    "surgeonfish": "deep", "damselfish": "deep", "butterflyfish": "deep",
    "wrasse": "elongate", "bottom": "elongate",
    "shark": "shark", "ray": "ray",
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

# Sides to the body and rings from nose to tail. Fine enough that a mark is
# a mark: at twenty by thirty a sweetlips' round spots came out as streaks and
# a threadfin's chevrons as smears, because a colour per vertex cannot hold a
# pattern finer than the vertices. Still a few thousand points a species,
# shared by every fish of it.
AROUND = 56
ALONG = 60

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


def body(form, bend: float = 0.0):
    """One fish, a metre long, nose at +x. See `anatomy`."""
    points, faces, _ = anatomy(form, bend)
    return points, faces


def form_of(kind) -> dict:
    """A species' or a group's whole form: its plan's, with what its sheet
    says of its own put over it."""
    if isinstance(kind, dict):
        return dict(kind)
    sheets = _sheets()
    if kind in PLANS:
        plan, own = kind, {}
    elif kind in sheets:
        plan, own = sheets[kind]["plan"], sheets[kind].get("form") or {}
    else:
        plan, own = OF_GROUP[kind], {}
    return {**FORM_DEFAULTS, **PLANS[plan], **own, "plan": plan}


def anatomy(form, bend: float = 0.0):
    """One fish, a metre long, nose at +x, and which part each vertex is.

    A body of elliptical rings whose height and width follow the outline; a
    tail of its form's shape; a dorsal fin along the back and an anal fin
    under it; two pectoral fins behind the gills; and two eyes. Fins are
    membranes, so they are thin surfaces drawn from both sides. Parts: 0 body,
    1 fin, 2 eye. `form` is a plan's name, a species', or a form (`form_of`).
    """
    says = form_of(form)
    if says["plan"] == "ray":
        return ray(says, bend)
    points, faces, parts = [], [], []

    def add(pts, fcs, part):
        at = len(points)
        points.extend(pts)
        faces.extend([tuple(at + i for i in f) for f in fcs])
        parts.extend([part] * len(pts))

    xs = np.linspace(0.0, 1.0 - says["tail"], ALONG)
    shoulder = says["nose"] + 0.18
    # The outline, as two curves meeting at its deepest point a third of the
    # way back: an ellipse in front, so the snout is rounded (a shark's is
    # pointed: `snout` above a half sharpens it), and a fuller curve behind,
    # because a fish stays deep and then narrows hard to a stalk before the
    # tail. The first version peaked at the head and tapered in a straight
    # cone, and every fish was a teardrop.
    u = xs / max(1.0 - says["tail"], 1e-6)
    peak = float(np.clip(says["nose"] + 0.30, 0.32, 0.48))
    front = np.power(np.clip(1.0 - ((peak - u) / peak) ** 2, 0.0, 1.0), says.get("snout", 0.5))
    behind = np.power(np.clip(1.0 - ((u - peak) / (1.0 - peak)) ** 2, 0.0, 1.0), says.get("fullness", 0.7))
    shape = np.where(u < peak, front, behind)
    stalk = says.get("stalk", 0.16)
    fat = np.clip(stalk + (1.0 - stalk) * shape, 0.05, 1.0)
    fat[0] = max(fat[0], 0.08)
    # A forehead: a bump on the back over the eyes (a unicornfish's, a
    # Napoleon wrasse's), raising only the upper half of the rings there.
    hump = says["hump"] * np.exp(-((xs - 0.75 * shoulder) / max(0.6 * shoulder, 1e-6)) ** 2)

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
            up = says["deep"] * fat[i] * np.cos(a)
            if up > 0:
                up += says["deep"] * hump[i] * np.cos(a) ** 2
            ring.append((0.5 - x, says["wide"] * fat[i] * np.sin(a) + sway(x), up))
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
        lift = says["deep"] * (fat[i] + (hump[i] if up > 0 else 0.0))
        return (0.5 - xs[i], sway(xs[i]), up * lift)

    # The tail, of its form's shape.
    root = 1.0 - says["tail"]
    span = says["fin"] * 2.1 if says["plan"] != "disc" else says["deep"] * 0.75
    flick = sway(1.0) + 0.07 * bend
    tip = -0.5
    peduncle = says["deep"] * fat[-1]
    base = [(0.5 - root, sway(root), peduncle), (0.5 - root, sway(root), -peduncle)]
    shape = says["tailshape"]
    if shape == "shark":
        add(base + [(tip, flick, span * 1.25), (tip + 0.16, flick * 0.8, -span * 0.55),
                    (tip + 0.11, flick * 0.9, 0.0)],
            [(0, 2, 4), (1, 4, 3), (0, 4, 1)], 1)
    elif shape in ("rounded", "truncate"):
        # A fan from the middle of the peduncle to a rim: bowed back in the
        # middle for a rounded tail, straight across for a truncate one.
        n = 7
        bow = 0.07 if shape == "rounded" else 0.0
        rim = [(tip + bow * (1.0 - np.cos(a)), flick, span * 0.75 * np.sin(a))
               for a in np.linspace(-np.pi / 2, np.pi / 2, n)]          # bottom to top
        mid = (0.5 - root, sway(root), 0.0)
        fan = [(2, 3 + k, 4 + k) for k in range(n - 1)]
        add(base + [mid] + rim, fan + [(0, 2, 3 + n - 1), (1, 3, 2)], 1)
    else:
        # Forked, or lunate: a deeper notch and longer lobes.
        deep_notch = 0.13 if shape == "forked" else 0.24
        reach = 1.0 if shape == "forked" else 1.25
        add(base + [(tip, flick, span * reach), (tip + deep_notch, flick * 0.85, 0.0), (tip, flick, -span * reach)],
            [(0, 2, 3), (1, 3, 4), (0, 3, 1)], 1)

    # The dorsal fin, of its form's kind.
    def membrane(stations, height_at, up=1):
        fin = []
        for n, along in enumerate(stations):
            base = at_body(along, up)
            fin += [base, (base[0] - 0.03, base[1], base[2] + up * height_at(n, along))]
        m = len(stations)
        if up > 0:
            return fin, ([(2 * n, 2 * n + 2, 2 * n + 1) for n in range(m - 1)]
                         + [(2 * n + 1, 2 * n + 2, 2 * n + 3) for n in range(m - 1)])
        return fin, ([(2 * n, 2 * n + 1, 2 * n + 2) for n in range(m - 1)]
                     + [(2 * n + 1, 2 * n + 3, 2 * n + 2) for n in range(m - 1)])

    kind = says["dorsal"]
    if kind == "shark":
        first = np.linspace(0.30, 0.46, 5)
        add(*membrane(first, lambda n, a: says["fin"] * (1.0 - abs(n - 1.2) / 3.0)), 1)
        second = np.linspace(0.68, 0.74, 3)
        add(*membrane(second, lambda n, a: says["fin"] * 0.25), 1)
    elif kind == "tall":
        st = np.linspace(0.15, 0.72, 9)
        add(*membrane(st, lambda n, a: says["fin"] * np.sin(np.pi * (n + 0.5) / 9) ** 0.6), 1)
    elif kind == "banner":
        st = np.linspace(0.18, 0.72, 8)
        add(*membrane(st, lambda n, a: says["fin"] * (4.5 if n == 1 else 1.4 if n == 0 else 1.0 - 0.6 * n / 7)), 1)
    elif kind == "low":
        st = np.linspace(0.20, 0.80, 9)
        add(*membrane(st, lambda n, a: says["fin"] * (0.8 + 0.2 * np.sin(np.pi * n / 8))), 1)
    else:
        st = np.linspace(0.22, 0.72, 7)
        add(*membrane(st, lambda n, a: says["fin"] * (1.0 - 0.6 * n / 6)), 1)
    # An anal fin under the back half.
    if says["anal"] > 0:
        st = np.linspace(0.48 if kind != "tall" else 0.3, 0.74, 4 if kind != "tall" else 8)
        k = len(st)
        add(*membrane(st, lambda n, a: says["fin"] * says["anal"] * (0.7 if kind != "tall" else
                                                                     np.sin(np.pi * (n + 0.5) / k) ** 0.6), up=-1), 1)
    # Pectoral fins behind the gills, swept back and a little down.
    i = int(0.24 / (1.0 - says["tail"]) * (ALONG - 1))
    size = says["pectoral"]
    for side in (1.0, -1.0):
        y = side * says["wide"] * fat[i]
        add([(0.5 - xs[i], y, 0.0), (0.5 - xs[i] - 0.03 * size, y, -0.05 * size * says["deep"] / 0.3),
             (0.5 - xs[i] - 0.16 * size, y + side * 0.06 * size, -0.02 * size)], [(0, 1, 2)], 1)
    # And the eyes: a dark ball each side of the head.
    i = int(0.09 / (1.0 - says["tail"]) * (ALONG - 1))
    r = 0.035 if says["plan"] != "shark" else 0.018
    for side in (1.0, -1.0):
        centre = np.array([0.5 - xs[i], side * says["wide"] * fat[i] * 0.85, says["deep"] * fat[i] * 0.3])
        add(*_ball(centre, r), 2)

    return (np.array(points, dtype="float32"), np.array(faces, dtype="int32"),
            np.array(parts, dtype="int8"))


FAUNA = __import__("pathlib").Path(__file__).resolve().parent / "fauna"


def scanned(kind: str):
    """A species' scanned model, when it has one (tools/fish-models/build):
    points a metre nose to tail, faces, uv per point, and its texture's path.
    None when it has none, and the grown form is drawn instead."""
    here = FAUNA / str(kind) / "model.npz"
    if not here.exists():
        return None
    got = np.load(here)
    return {"points": got["points"], "faces": got["faces"], "uv": got["uv"],
            "texture": str(FAUNA / str(kind) / "texture.jpg"),
            "ray": _sheets().get(kind, {}).get("plan") == "ray"}


def swum(model: dict, bend: float = 0.0) -> np.ndarray:
    """A scanned fish's points as it swims: the same travelling wave down the
    back half that a grown fish swims with, or a ray's wings lifted and
    lowered."""
    p = np.array(model["points"], dtype="float32", copy=True)
    if model["ray"]:
        span = max(float(np.abs(p[:, 1]).max()), 1e-6)
        p[:, 2] += 0.22 * bend * (np.abs(p[:, 1]) / span) ** 1.6
        return p
    along = np.clip(0.5 - p[:, 0], 0.0, 1.0)            # 0 at the nose, 1 at the tail
    p[:, 1] += 0.11 * bend * along ** 2 * np.sin(np.pi * 1.4 * along)
    return p


def _ball(centre, r):
    ball, cells = [], []
    for a in range(7):
        for b in range(10):
            th, ph = np.pi * a / 6, 2 * np.pi * b / 10
            ball.append(tuple(np.asarray(centre) + r * np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)])))
    for a in range(6):
        for b in range(10):
            q, w = a * 10 + b, a * 10 + (b + 1) % 10
            cells += [(q, q + 10, w), (w, q + 10, w + 10)]
    return ball, cells


def ray(says: dict, bend: float = 0.0):
    """A ray, a metre nose to tail: a diamond disc that flies on its wings
    (`bend` lifts and lowers them), a head out in front of it, a whip of a
    tail. Parts as `anatomy`'s: the disc is body, the tail a fin."""
    points, faces, parts = [], [], []

    def add(pts, fcs, part):
        at = len(points)
        points.extend(pts)
        faces.extend([tuple(at + i for i in f) for f in fcs])
        parts.extend([part] * len(pts))

    disc = 1.0 - says["tail"]                    # nose to the back of the disc
    head = says["nose"]
    span = says["wide"]                          # half the wingspan
    xs = np.linspace(0.0, disc, 22)              # 0 at the nose
    # Half-width along the disc: a head, then the wings out to their tips a
    # third of the way back, and in again to the tail.
    tip_at = head + 0.28 * (disc - head)
    half = np.where(xs < head, 0.35 * span * np.sqrt(xs / max(head, 1e-6)),
                    np.where(xs < tip_at, 0.35 * span + 0.65 * span * (xs - head) / max(tip_at - head, 1e-6),
                             span * (1.0 - (xs - tip_at) / max(disc - tip_at, 1e-6)) ** 0.9))
    half = np.maximum(half, 0.01)
    across = np.linspace(-1.0, 1.0, 17)
    grid = []
    for i, x in enumerate(xs):
        for u in across:
            y = u * half[i]
            # Thick in the middle, a membrane at the edge, and the wings
            # lifted and lowered as it flies.
            z = says["deep"] * (1.0 - u * u) * (1.0 - 0.6 * x / disc) + 0.22 * bend * (abs(y) / span) ** 1.6
            grid.append((0.5 - x, y, z))
    cells = []
    n = len(across)
    for i in range(len(xs) - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j, (i + 1) * n + j + 1
            cells += [(a, c, b), (b, c, d)]
    add(grid, cells, 0)
    # The tail: a thin wedge to the back, swinging a little.
    root = 0.5 - disc
    add([(root, -0.012, 0.0), (root, 0.012, 0.0), (-0.5, 0.03 * bend, 0.0), (root, 0.0, 0.012)],
        [(0, 2, 1), (0, 3, 2), (1, 2, 3)], 1)
    # Eyes at the sides of the head.
    for side in (1.0, -1.0):
        add(*_ball((0.5 - 0.6 * head, side * 0.3 * span, says["deep"] * 0.6), 0.012), 2)
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


def marked(points, mark: str, plan: str, parts=None) -> tuple[np.ndarray, np.ndarray]:
    """Where one of a species' marks is on the body: (mark, edge) masks.

    The marks that name a reef fish at a glance — a clownfish's three white
    bands, a copperband's bars, a foureye's false eye by its tail, a wrasse's
    stripes, a tang's tail; and the Red Sea's, read off the Jeddah tank's
    fish: a sweetlips' dense black spots, a twobar bream's two head bars, a
    yellowbar angel's bar, a sergeant's five, a threadfin's chevrons and
    yellow rear, a blacktip's tips, a grouper's blotches, a batfish's bars,
    a half-and-half chromis's halves, a bannerfish's bands. `edge` is a thin
    dark rim, which bands and eyespots have."""
    x, z = points[:, 0], points[:, 2]
    along = 0.5 - x                                  # 0 at the nose, 1 at the tail
    height = np.clip((z - z.min()) / max(1e-6, z.max() - z.min()), 0.0, 1.0)
    on_body = np.ones(len(points), dtype=bool) if parts is None else parts == 0
    on_fins = np.zeros(len(points), dtype=bool) if parts is None else parts == 1
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
    elif mark == "dots":
        # Small round spots, densely, over body and fins.
        accent = ((np.sin(along * 95.0) * np.sin(z * 95.0 + 0.7 * np.sin(along * 30.0))) > 0.80) & (along > 0.12)
    elif mark == "headbars":
        slant = along + 0.12 * (height - 0.5)
        accent = on_body & (((slant > 0.075) & (slant < 0.115)) | ((slant > 0.19) & (slant < 0.235)))
    elif mark == "eyebar":
        slant = along + 0.10 * (height - 0.5)
        accent = on_body & (slant > 0.065) & (slant < 0.12)
    elif mark == "bar":
        accent = on_body & (along > 0.40) & (along < 0.50) & (height > 0.18) & (height < 0.92)
    elif mark == "sergeant":
        accent = on_body & (np.sin(along * 2.0 * np.pi * 5.0 - 0.6) > 0.55) & (along > 0.18) & (along < 0.82) \
            & (height > 0.22)
    elif mark == "chevrons":
        lines = (np.sin((along + 0.9 * height) * 2.0 * np.pi * 5.0) > 0.70) & (along < 0.55)
        lines |= (np.sin((along - 0.9 * height) * 2.0 * np.pi * 5.0) > 0.70) & (along >= 0.55) & (along < 0.72)
        accent = on_body & lines & (along > 0.14)
    elif mark == "rear":
        accent = (along > 0.62) & (height > 0.3)
    elif mark == "tips":
        accent = on_fins & ((height > 0.90) | (height < 0.05) | (along > 0.965))
    elif mark == "blotches":
        n = (np.sin(along * 13.0 + 1.3) * np.sin(z * 11.0 + 0.4) + 0.6 * np.sin(along * 7.0 - z * 9.0 + 2.0))
        accent = (n > 0.55) & (along > 0.08) & (along < 0.95)
    elif mark == "batfish":
        accent = on_body & (((along > 0.05) & (along < 0.12)) | ((along > 0.25) & (along < 0.33)))
    elif mark == "half":
        accent = along < 0.52
    elif mark == "checker":
        accent = on_body & ((np.sin(along * 42.0) > 0) ^ (np.sin(z * 42.0) > 0)) & (along > 0.2) & (along < 0.8)
    elif mark == "mask":
        accent = on_body & (along > 0.05) & (along < 0.16) & (height > 0.45) & (height < 0.8)
    elif mark == "banner":
        slant = along + 0.30 * (height - 0.5)
        accent = on_body & (((slant > 0.16) & (slant < 0.30)) | ((slant > 0.48) & (slant < 0.62)))
    elif mark == "back":
        accent = on_body & (height > 0.62)
    elif mark == "belly":
        accent = on_body & (height < 0.35)
    elif mark == "fins":
        accent = on_fins
    return accent, edge


# What colour a mark is drawn in when the sheet does not say: its accent, or
# near black.
DARK_MARKS = {"dots", "headbars", "eyebar", "sergeant", "chevrons", "tips", "blotches",
              "batfish", "half", "checker", "banner", "eyespot"}
DARK = (0.025, 0.025, 0.03)


def marks_of(sheet: dict) -> list:
    """A sheet's marks as (name, colour) pairs. `mark` is the old single mark
    in the accent; `marks` a list of names or (name, colour)."""
    accent = tuple(sheet["palette"][2])
    if "marks" in sheet:
        out = []
        for one in sheet["marks"]:
            name, colour = (one, None) if isinstance(one, str) else (one[0], tuple(one[1]))
            out.append((name, colour if colour is not None else (DARK if name in DARK_MARKS else accent)))
        return out
    mark = sheet.get("mark", "none")
    return [] if mark == "none" else [(mark, accent)]


def painted(points, group: str, rng, parts=None) -> np.ndarray:
    """A colour per vertex: dark back, pale belly, and the accent where it sits
    on that fish — bands, stripes, bars, an eyespot, spots, a tail. A species
    is painted from its own sheet; a behaviour group from the group's."""
    sheets = _sheets()
    if group in sheets:
        sheet = sheets[group]
        lit = rng.uniform(0.95, 1.05)
        back, belly, accent = (np.array(c) * lit for c in sheet["palette"])
        colour = _shaded(points, back, belly)
        if parts is not None and sheet.get("fins") is not None:
            colour[parts == 1] = np.array(sheet["fins"]) * lit
        for name, tint in marks_of(sheet):
            where, rim = marked(points, name, sheet["plan"], parts)
            colour[where] = np.array(tint) * lit
            colour[rim] = (0.03, 0.03, 0.035)
        return _finished(colour, accent, parts, fins_given=sheet.get("fins") is not None)
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


def _finished(colour, accent, parts, fins_given: bool = False) -> np.ndarray:
    if parts is not None:
        # Fins carry the body's colour lightened towards the accent, unless
        # the sheet says what colour they are; and the eye is a dark ball
        # with nothing painted on it.
        if not fins_given:
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
