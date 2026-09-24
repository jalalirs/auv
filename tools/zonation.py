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
# Which reef. The shapes are the same everywhere; the mix is not.
#
# The bands below were read off Caribbean and Red Sea fore-reef surveys
# together, and used for every place on the platform. That is wrong in a way
# that shows: they are heavy in *fans* at depth, and a gorgonian sea fan is a
# Caribbean signature. The Red Sea has very few of them. What it has instead
# is Acropora tables on the slope and soft corals — Xenia, Sarcophyton,
# Dendronephthya — which are a different shape and a different colour.
#
# Al Fahal is the reef that made this worth fixing: sixty-seven of the
# sixty-eight dives on this platform happen there, and it was being drawn as
# a Caribbean reef.
ASSEMBLAGES = {}

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


# The Caribbean mix is the one above, named so a place can ask for it.
ASSEMBLAGES["caribbean"] = BANDS

# And the Red Sea, off what somebody counted on this reef.
#
# Al Fahal is a midshelf reef in the Thuwal group, surveyed by line intercept
# on ten-metre transects at two and ten metres — Roberts et al., "Spatial
# variation in coral reef fish and benthic communities in the central Saudi
# Arabian Red Sea", PeerJ 5:e3410, 2017, which recorded twenty-five
# scleractinian genera across nine reefs and found Porites, Pocillopora and
# Acropora each above five per cent of benthic cover. Transects in August 2024
# put those three at 63.8% of coral cover between them — Porites 34.6,
# Pocillopora 22.8, Acropora 6.4.
#
# Turning genera into the shapes this platform draws:
#
#   Porites       massive. The great smooth boulders, and the single most
#                 abundant thing on the reef.
#   Pocillopora   branching, small and bushy rather than staghorn thickets.
#   Acropora      table on the slope, branching in the shallows. Tables are
#                 the shape a Red Sea fore reef is known for and the shape the
#                 Caribbean does not have at all.
#   the rest      Stylophora branching, Millepora and Montipora encrusting and
#                 plating, Favia and Platygyra brain, and soft corals which
#                 this palette draws as plumes.
#
# So: massive and branching carry the reef, tables appear on the slope and
# peak at ten to twenty metres, and fans nearly disappear.
ASSEMBLAGES["red-sea"] = (
    # The flat and the crest, scoured. Nothing delicate survives here.
    (2.0, {"encrusting": 0.26, "rubble": 0.22, "massive": 0.24,
           "branching": 0.16, "finger": 0.06, "plume": 0.04,
           "sponge": 0.02}, 0.55),
    # Upper fore reef: Porites boulders and Pocillopora, tables beginning.
    (4.5, {"massive": 0.28, "branching": 0.22, "encrusting": 0.12,
           "table": 0.10, "finger": 0.09, "plume": 0.08, "brain": 0.06,
           "rubble": 0.03, "sponge": 0.02}, 1.70),
    # The slope, which is the postcard: tables over boulders.
    (10.0, {"massive": 0.26, "table": 0.20, "branching": 0.16,
            "plume": 0.11, "encrusting": 0.09, "brain": 0.08,
            "finger": 0.05, "sponge": 0.04, "fan": 0.01}, 2.30),
    (18.0, {"table": 0.24, "massive": 0.21, "plume": 0.14,
            "encrusting": 0.12, "brain": 0.10, "branching": 0.08,
            "sponge": 0.07, "fan": 0.02, "rubble": 0.02}, 2.30),
    # Deeper, where light is a tenth and a colony spreads to catch it.
    (26.0, {"encrusting": 0.24, "table": 0.20, "massive": 0.16,
            "sponge": 0.14, "plume": 0.13, "brain": 0.08,
            "fan": 0.03, "branching": 0.02}, 2.00),
    (999.0, {"encrusting": 0.30, "sponge": 0.22, "table": 0.18,
             "massive": 0.14, "plume": 0.10, "fan": 0.04,
             "brain": 0.02}, 1.70),
)


# And Hawaii, which is the odd one of the three.
#
# Kāne'ohe Bay is two species and a third: *Porites compressa*, finger coral,
# which builds the bay's patch reefs; *Montipora capitata*, rice coral,
# encrusting and plating and sometimes branching; and *Porites lobata*, the
# lobe coral, massive. The two-thousand-fourteen baseline for the bay's
# mitigation bank put cover between 37.9 and 88.0 per cent across its reefs,
# which is high — these are not degraded reefs.
#
# What matters for a picture is the two shapes that are *missing*. The main
# Hawaiian islands have essentially no Acropora, so there are **no tables** —
# the shape the Red Sea slope is known for does not occur here at all. And
# there are no shallow gorgonian sea fans. An archipelago four thousand
# kilometres from anywhere has a short species list, and a reef drawn from a
# general idea of a reef gets it wrong in exactly the way a diver would
# notice first.
ASSEMBLAGES["hawaii"] = (
    # The reef flat and the tops of the patch reefs.
    (2.0, {"finger": 0.30, "encrusting": 0.24, "massive": 0.18,
           "rubble": 0.16, "branching": 0.08, "sponge": 0.04}, 0.55),
    # The sides of the patch reefs, which is where the finger coral is.
    (4.5, {"finger": 0.34, "encrusting": 0.22, "massive": 0.18,
           "branching": 0.12, "rubble": 0.06, "brain": 0.04,
           "sponge": 0.04}, 1.50),
    (10.0, {"finger": 0.28, "encrusting": 0.26, "massive": 0.20,
            "branching": 0.10, "sponge": 0.07, "brain": 0.05,
            "plume": 0.04}, 1.80),
    # The lagoon floor and below, where it goes to plates and sand.
    (18.0, {"encrusting": 0.32, "massive": 0.20, "finger": 0.16,
            "sponge": 0.14, "branching": 0.08, "plume": 0.06,
            "brain": 0.04}, 1.70),
    (26.0, {"encrusting": 0.36, "sponge": 0.22, "massive": 0.16,
            "plume": 0.12, "finger": 0.08, "brain": 0.06}, 1.50),
    (999.0, {"encrusting": 0.40, "sponge": 0.28, "massive": 0.14,
             "plume": 0.12, "brain": 0.06}, 1.30),
)


# And the deep, which is not a reef and must not be drawn as one.
#
# Five hundred metres down there is no light, so there is no zooxanthellate
# coral — nothing that builds a reef builds anything here. What is down there
# feeds on what falls: black corals standing in the current as whips and
# fans, sponges, and a sediment plain between them that is mostly empty.
#
# The Red Sea deep is among the least explored in the world. The Red Sea
# Decade Expedition's ROV surveys ran from thirty-eight metres to one
# thousand seven hundred and eighty-three, and found a hundred and forty-three
# taxa in fifty-three families — including black corals, which are the
# standing shapes at this depth.
#
# Two things about this mix. It has no depth structure worth the name, because
# nothing here is set by light: the bands are flat and the only reason there
# is more than one is that the palette wants them. And it is *sparse* — how
# sparse is set by the colony count a place is built with, not here, and for
# Thuwal Deep that is a few hundred a square kilometre against a reef's
# hundreds of thousands.
ASSEMBLAGES["deep"] = (
    (2.0, {"sponge": 0.44, "encrusting": 0.34, "plume": 0.22}, 0.80),
    (4.5, {"sponge": 0.44, "encrusting": 0.32, "plume": 0.24}, 1.00),
    (10.0, {"sponge": 0.42, "plume": 0.30, "encrusting": 0.28}, 1.20),
    (18.0, {"plume": 0.36, "sponge": 0.36, "encrusting": 0.28}, 1.40),
    (26.0, {"plume": 0.38, "sponge": 0.36, "encrusting": 0.26}, 1.60),
    # Everything Thuwal Deep actually is falls in this band: whips standing in
    # the current, sponges, and crusts on whatever rock the sediment has not
    # buried.
    (999.0, {"plume": 0.40, "sponge": 0.36, "encrusting": 0.24}, 1.80),
)


def bands_for(assemblage: str | None):
    """The mix for a named reef, or the one this platform started with."""
    if assemblage is None:
        return BANDS
    try:
        return ASSEMBLAGES[str(assemblage).lower()]
    except KeyError:
        raise KeyError(
            f"no assemblage called {assemblage!r}; "
            f"there is {', '.join(sorted(ASSEMBLAGES))}") from None


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


def describe(height, across: float, picture=None) -> dict:
    """Read a seabed and say what kind of ground each square metre of it is.

    `picture` is the place photographed from above, when there is one, as rows
    of RGB. Where it exists it is believed over the inference: whether ground
    is rock or sand is a thing a picture of it shows directly, and working it
    out from the slope instead is guessing at something already observed. Sand
    is the brightest thing on a reef from above — it reflects where coral and
    rock absorb — so the darker half of a lit seabed is the living half.
    """
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

    if picture is not None:
        seen = _hard_from_picture(picture, depth.shape)
        if seen is not None:
            # Two thirds the picture, one third the shape. Not all of the
            # picture, because at ten metres a pixel a patch of coral smaller
            # than a tennis court averages away into the sand around it, and
            # the shape still knows that ground standing proud is swept.
            hard = np.clip(0.67 * seen + 0.33 * hard, 0.02, 1.0)

    ceiling = np.interp(depth, DEPTH_M, COVER)

    # A wall sheds everything that lands on it.
    standing = np.clip(1.0 - (slope - 45.0) / 25.0, 0.12, 1.0)

    return {"depth": depth, "slope": slope, "stands": stands,
            "hard": hard, "ceiling": ceiling, "standing": standing,
            "step": step}


def _hard_from_picture(picture, shape):
    """How much of each cell is not sand, from the light coming off it."""
    picture = np.asarray(picture, dtype="float64")
    if picture.ndim == 3 and picture.shape[0] == 3:
        picture = np.transpose(picture, (1, 2, 0))
    if picture.ndim != 3 or picture.shape[2] < 3:
        return None
    if picture.shape[:2] != tuple(shape):
        rows = (np.arange(shape[0]) * picture.shape[0] // shape[0]).clip(0, picture.shape[0] - 1)
        cols = (np.arange(shape[1]) * picture.shape[1] // shape[1]).clip(0, picture.shape[1] - 1)
        picture = picture[np.ix_(rows, cols)]
    brightness = picture[..., :3].mean(axis=2)
    lit = brightness > 1.0                    # anything the sun reached at all
    if lit.sum() < 50:
        return None
    # Stretched against this reef's own sand rather than an absolute: how
    # bright a seabed photographs depends on the water over it, and a threshold
    # that works at Looe Key is wrong at twenty metres in the Red Sea.
    sand, dark = np.percentile(brightness[lit], 85), np.percentile(brightness[lit], 15)
    if sand - dark < 1e-6:
        return None
    return np.clip((sand - brightness) / (sand - dark), 0.0, 1.0)


# What the bottom between the colonies is made of, and what each of those
# actually looks like at arm's length, white balanced. Not the coral: the
# colonies are their own geometry with their own materials, so this is the
# substrate they sit on — which is the part that was coming out black.
#
# Carbonate sand is very pale and slightly warm; rubble is a tan of broken
# skeleton; pavement is rock under turf and algae, which is the darkest and the
# only one with much green in it.
SUBSTRATE = {
    "sand":     (226, 214, 188),
    "rubble":   (176, 162, 138),
    "pavement": (126, 122, 100),
}


def substrate_colour(height, across: float, picture=None):
    """The seabed's own colour, from what the ground is rather than from a
    photograph of it.

    A satellite picture of a reef is not an albedo map: the light in it has
    been down through fifteen metres of water and back, and a renderer that
    treats it as the bottom's own colour attenuates it a second time — the
    ground goes black under coral that is lit, which is exactly what the first
    reef dive looked like.

    Taking the water back out is possible and is not enough. Red is gone in
    four metres, so over a reef in fifteen the red band holds no bottom signal
    at all and there is nothing there to recover. What the surviving bands do
    say, clearly, is *where* things are: sand is the brightest thing on a reef
    from above and pavement the darkest.

    So the picture classifies and the class carries the colour. Brightness
    inside a class still modulates it, because a reef is not three flat
    colours and the picture knows about the metre-scale variation even where
    it cannot say what colour it is.
    """
    ground = describe(height, across, picture=picture)
    hard = ground["hard"]
    rows, columns = hard.shape

    # Three ways to be bottom, as weights that sum to one everywhere. Sand
    # where nothing is hard, pavement where everything is, rubble between —
    # which is what rubble actually is.
    sand = np.clip(1.0 - hard * 1.6, 0.0, 1.0)
    pavement = np.clip((hard - 0.45) / 0.4, 0.0, 1.0)
    rubble = np.clip(1.0 - sand - pavement, 0.0, 1.0)
    total = np.maximum(1e-6, sand + rubble + pavement)

    colour = np.zeros((rows, columns, 3), dtype="float64")
    for weight, kind in ((sand, "sand"), (rubble, "rubble"), (pavement, "pavement")):
        for band in range(3):
            colour[..., band] += (weight / total) * SUBSTRATE[kind][band]

    if picture is not None:
        seen = _hard_from_picture(picture, hard.shape)
        if seen is not None:
            # Keep the metre-scale variation the picture does know about,
            # gently: a fifth either way, so a reef has grain without the
            # picture's own cast coming back with it.
            lit = np.asarray(picture, dtype="float64")
            if lit.ndim == 3 and lit.shape[0] == 3:
                lit = np.transpose(lit, (1, 2, 0))
            if lit.shape[:2] != hard.shape:
                r = (np.arange(rows) * lit.shape[0] // rows).clip(0, lit.shape[0]-1)
                c = (np.arange(columns) * lit.shape[1] // columns).clip(0, lit.shape[1]-1)
                lit = lit[np.ix_(r, c)]
            grey = lit[..., :3].mean(axis=2)
            wet = grey > 1.0
            if wet.sum() > 50:
                middle = np.median(grey[wet])
                grain = np.clip(1.0 + 0.2 * (grey - middle) / max(1.0, middle), 0.8, 1.2)
                colour *= grain[..., None]

    return np.clip(colour, 0, 255).astype("uint8")


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


def community(depths, rng, bands=None):
    """Which kind of coral each colony is, and how big it may get.

    Sampled per colony from the band it landed in, rather than from one mix for
    the whole site. One mix is how a reef ends up with staghorn thickets on the
    crest where the waves break them and boulder heads at thirty metres where
    there is no light to build them with.
    """
    bands = BANDS if bands is None else bands
    # Every kind in the palette, not only the ones this assemblage uses, so a
    # reef's prototypes line up with its weights whichever mix it was grown
    # from.
    kinds = sorted({kind for mix in ASSEMBLAGES.values()
                    for _, weights, _ in mix for kind in weights})
    index = {kind: i for i, kind in enumerate(kinds)}

    edges = np.array([deepest for deepest, _, _ in bands])
    band = np.searchsorted(edges, np.asarray(depths), side="left")
    band = np.clip(band, 0, len(bands) - 1)

    table = np.zeros((len(bands), len(kinds)))
    caps = np.zeros(len(bands))
    for b, (_, weights, cap) in enumerate(bands):
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

    `between` is a reef-diving band and it is the right one for every place on
    this platform that is a reef. It is not right for a place that is not.
    Thuwal Deep runs from five hundred and nineteen metres to six hundred and
    thirty-eight, so no cell on it was ever inside eight to eighteen, this
    returned None, and the site fell back to the start meant for ground with
    nothing growing on it — on a site carrying twenty thousand colonies. Every
    frame it has ever produced was of empty mud, and the record beside them
    said, in so many words, "there is no reef here to begin at".

    A band that contains none of the site is not a band, it is a filter that
    rejected everything. When that happens the site's own middle half of its
    depth range is used instead: a vehicle works where the place is.
    """
    depth = ground["depth"]
    rows, columns = depth.shape
    step = across / max(1, columns - 1)

    inside = (depth >= between[0]) & (depth <= between[1])
    why = "the band a vehicle works a reef in, %g to %g m" % between
    if not inside.any():
        low, high = (float(np.percentile(depth, 25)),
                     float(np.percentile(depth, 75)))
        inside = (depth >= low) & (depth <= high)
        why = ("the middle half of this site's own depths, %.0f to %.0f m: "
               "nothing here is between %g and %g, which is the band a reef "
               "is dived in and not a band this place has"
               % (low, high, between[0], between[1]))
    good = np.where(inside, cover, 0.0)
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
        "within": why,
    }
