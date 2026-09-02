"""Where on a reef each thing grows.

Coral does not thin smoothly with depth. A reef has parts, the parts are in a
fixed order, and which part you are standing on decides not only how much coral
there is but what shape it is. Four metres down on the fore reef is eighty per
cent cover of tables and thickets; two metres down on the flat behind the crest
is a scoured rubble pavement with encrusting colonies and nothing standing more
than a hand's width off it. Same light, same water, twenty metres apart.

Three things decide it, and only one of them was in the first version:

  light      falls about ten per cent a metre in clear tropical water, so it
             sets the ceiling and nothing else does below twenty metres;
  wave       peaks in the top few metres and scours them, which is why the
             shallowest ground is not the richest and why nothing delicate
             grows there;
  substrate  coral needs rock. Sand collects in the low ground between spurs
             and on the flats beyond them, and coral cannot attach to it. This
             is the term that makes a plan view read as a reef rather than as a
             depth gradient — without it every contour looks the same all the
             way along, which is exactly what the first reef looked like.

Nothing here is specific to one site. It reads a heightfield and works out where
the reef's parts are from the ground itself, so it applies to surveyed terrain
and constructed terrain alike.
"""

from __future__ import annotations

import numpy as np

# Cover a reef can hold at a given depth, with rock under it and nothing else
# against it. Read off Caribbean and Red Sea fore-reef surveys: the peak is at
# four to ten metres, not at the surface, because the surface is where the waves
# are. Below twenty-five metres it is plates and sponges and falling.
DEPTH_M = (0.0, 1.0, 2.5, 4.0, 8.0, 14.0, 20.0, 25.0, 30.0, 36.0, 60.0)
COVER = (0.10, 0.42, 0.34, 0.76, 0.84, 0.74, 0.56, 0.42, 0.26, 0.15, 0.04)

# What grows there, by depth. The shallow end is built to survive being hit:
# encrusting sheets, low boulders, rubble. The middle is the postcard — tables
# and thickets. The deep end flattens out into plates and fans, which is what
# catching a tenth of the light does to a colony's shape.
#
# Each band is (deepest metre, weights by kind, the biggest a colony gets).
BANDS = (
    (2.0, {"encrusting": 0.28, "rubble": 0.24, "massive": 0.20,
           "branching": 0.09, "finger": 0.09, "plume": 0.06,
           "sponge": 0.04}, 0.55),
    (4.5, {"massive": 0.17, "plume": 0.16, "branching": 0.15, "finger": 0.12,
           "encrusting": 0.10, "fan": 0.09, "rubble": 0.08, "sponge": 0.07,
           "brain": 0.06}, 1.70),
    (10.0, {"plume": 0.20, "fan": 0.16, "massive": 0.15, "branching": 0.11,
            "finger": 0.09, "sponge": 0.08, "brain": 0.07, "table": 0.06,
            "encrusting": 0.05, "rubble": 0.03}, 2.20),
    (18.0, {"fan": 0.20, "plume": 0.17, "massive": 0.13, "sponge": 0.10,
            "table": 0.10, "brain": 0.08, "branching": 0.07, "finger": 0.06,
            "encrusting": 0.06, "rubble": 0.03}, 2.20),
    (26.0, {"fan": 0.20, "table": 0.16, "sponge": 0.14, "plume": 0.13,
            "massive": 0.12, "encrusting": 0.10, "brain": 0.08,
            "branching": 0.07}, 2.00),
    (999.0, {"table": 0.24, "fan": 0.18, "sponge": 0.18, "encrusting": 0.16,
             "plume": 0.10, "massive": 0.08, "brain": 0.06}, 1.70),
)


def _blur(field, metres: float, step: float):
    """Smoothed over about that many metres.

    Counted in metres rather than in passes. Repeating a four-neighbour average
    k times spreads it over roughly the square root of k samples, not k — so
    "twenty metres" asked for as twenty passes reaches about six, and a
    high-pass built on it sees almost nothing. Which is what happened: the term
    meant to tell a spur from a groove came out at one half everywhere.
    """
    passes = int(round(2.0 * (metres / max(step, 1e-6)) ** 2))
    passes = max(1, min(passes, 400))
    for _ in range(passes):
        field = 0.25 * (np.roll(field, 1, 0) + np.roll(field, -1, 0)
                        + np.roll(field, 1, 1) + np.roll(field, -1, 1))
    return field


def describe(height, across: float) -> dict:
    """Read a seabed and say what kind of ground each square metre of it is."""
    depth = -np.asarray(height, dtype="float64")
    rows, columns = depth.shape
    step = across / max(1, columns - 1)

    dy, dx = np.gradient(depth, across / max(1, rows - 1), step)
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))

    # How high this ground stands above what is around it, over about forty
    # metres. Positive is a spur, a head, a ridge — somewhere the current runs
    # over and the sand does not settle. Negative is a groove or a hollow, which
    # is where the sand goes.
    stands = -(_blur(depth, 2.5, step) - _blur(depth, 22.0, step))

    # Rock or sand. Sand fills the low ground and lies flat; anything standing
    # proud of its surroundings, or steep, is swept and stays hard.
    # Flat ground is pavement, not half sand. What sand does is fill the low
    # places, so this starts near one and falls away in the hollows rather than
    # sitting at a half everywhere and taking half the reef with it.
    hard = np.clip(0.88 + stands / 1.5, 0.0, 1.0)
    hard = np.maximum(hard, np.clip((slope - 3.0) / 12.0, 0.0, 1.0))
    # A wide flat plain is sand whatever its local relief says, because local
    # relief on a plain is noise.
    plain = np.clip(1.0 - slope / 2.5, 0.0, 1.0) * np.clip((depth - 22.0) / 8.0, 0.0, 1.0)
    hard *= 1.0 - 0.85 * plain
    hard = np.clip(hard, 0.02, 1.0)

    ceiling = np.interp(depth, DEPTH_M, COVER)

    # A wall sheds everything that lands on it.
    standing = np.clip(1.0 - (slope - 45.0) / 25.0, 0.12, 1.0)

    return {"depth": depth, "slope": slope, "stands": stands,
            "hard": hard, "ceiling": ceiling, "standing": standing,
            "step": step}


def cover(ground: dict, rng, patchiness: float = 1.0):
    """How much of each square metre the coral should cover.

    The ceiling the depth allows, times how much of the ground is rock, times
    the patchiness a reef has — coral recruits beside coral, so it comes in
    stands with clearings between them and never as an even lawn.
    """
    depth = ground["depth"]
    rows, columns = depth.shape
    step = ground["step"]

    wanted = ground["ceiling"] * ground["hard"] * ground["standing"]

    # Two scales of clearing: stands of a few metres, and reaches of a hundred
    # where a reef is simply better or worse than the reef next to it.
    def blobs(metres, strength):
        cells = max(2, int(round(rows * step / metres)))
        seed = rng.normal(0, 1, (cells, cells))
        up_r = (np.arange(rows) * cells // rows).clip(0, cells - 1)
        up_c = (np.arange(columns) * cells // columns).clip(0, cells - 1)
        field = _blur(seed[np.ix_(up_r, up_c)], metres / 3.0, step)
        return field / (field.std() or 1.0) * strength

    patch = 1.0 + patchiness * (blobs(24.0, 0.34) + blobs(110.0, 0.26))
    return np.clip(wanted * patch, 0.0, 0.94)


def community(depths, rng):
    """Which kind of coral each colony is, and how big it may get.

    Sampled per colony from the band it landed in, rather than from one mix for
    the whole site. One mix is how a reef ends up with staghorn thickets on the
    crest where the waves break them and boulder heads at thirty metres where
    there is no light to build them with.
    """
    kinds = sorted({kind for _, weights, _ in BANDS for kind in weights})
    index = {kind: i for i, kind in enumerate(kinds)}

    edges = np.array([deepest for deepest, _, _ in BANDS])
    band = np.searchsorted(edges, np.asarray(depths), side="left")
    band = np.clip(band, 0, len(BANDS) - 1)

    table = np.zeros((len(BANDS), len(kinds)))
    caps = np.zeros(len(BANDS))
    for b, (_, weights, cap) in enumerate(BANDS):
        for kind, weight in weights.items():
            table[b, index[kind]] = weight
        table[b] /= table[b].sum()
        caps[b] = cap

    # One draw each, against the cumulative weights of its own band.
    running = np.cumsum(table, axis=1)
    picked = (running[band] < rng.random(len(band))[:, None]).sum(axis=1)
    return kinds, np.clip(picked, 0, len(kinds) - 1), caps[band]


def best_ground(ground: dict, cover, across: float,
                between=(8.0, 18.0), off_bottom: float = 3.0):
    """Where on this site a dive should begin.

    The middle of a site is the right answer only when the site is uniform, and
    a reef is the opposite of uniform — its whole point is that the parts are
    different. On real ground the middle can be, and at Looe Key is, three
    metres of surf-scoured reef flat.

    So: the best reef inside the depth band a vehicle actually works in, far
    enough from the edge to fly in any direction, and with room underneath.
    """
    depth = ground["depth"]
    rows, columns = depth.shape
    step = across / max(1, columns - 1)

    good = np.where((depth >= between[0]) & (depth <= between[1]), cover, 0.0)
    # Not against the edge: a start point ten metres from the boundary is a
    # start point with one direction to go.
    margin = max(2, int(round(0.12 * rows)))
    edge = np.zeros_like(good)
    edge[margin:-margin, margin:-margin] = 1.0
    good = good * edge
    # Judged over a neighbourhood rather than a cell, so the answer is a good
    # area and not the single luckiest square metre in a bad one.
    good = _blur(good, 12.0, step)
    if good.max() <= 0:
        return None

    row, column = np.unravel_index(int(good.argmax()), good.shape)
    x = -across / 2 + column * step
    y = -across / 2 + row * step
    floor = float(-depth[row, column])
    return {
        "at": [round(float(x), 1), round(float(y), 1),
               round(floor + off_bottom, 1)],
        "depthM": round(float(depth[row, column]), 1),
        "coverThere": round(float(cover[row, column]), 2),
    }
