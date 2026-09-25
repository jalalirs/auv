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
import scanned
import zonation


def plant(where: pathlib.Path, height, across: float, seed: int,
          how_many: int, picture=None, reference: pathlib.Path | None = None,
          cover_from: str | None = None,
          assemblage: str | None = None) -> dict:
    """Grow a reef onto a seabed, and write it beside it.

    `reference` is a place's fetched corpus. Where it holds a scan of a colony
    of some growth form, that scan is used for that form instead of a grown
    shape. Museum specimens are dry skeletons, so they give the form, and the
    colour still comes from photographs of the reef itself.
    """
    # Where the density came from, and it has to come from somewhere.
    #
    # Everything below works out how much coral a square metre holds from the
    # depth, the hardness of the ground and a patchiness, which is a *model*
    # and not a measurement. That is a reasonable way to build a reef nobody
    # has counted; it is not a reasonable thing to publish without saying so.
    # Three of this platform's places carried densities from this model —
    # 44,000, 500,000 and 1.4 million colonies a square kilometre — against
    # the 83,055 that somebody actually counted at Looe Key, and nothing in
    # the record said which of the four was the measured one.
    if not cover_from:
        raise ValueError(
            "say where this reef's density comes from: a survey, or that it "
            "was chosen. A reef built without an answer to that is a number "
            "somebody will later cite as a measurement.")

    rng = np.random.default_rng(seed)
    rows, columns = height.shape
    depth = -height

    # What kind of ground this is, everywhere.
    ground = zonation.describe(height, across, picture=picture)
    want = zonation.cover(ground, rng)
    if want.sum() <= 0:
        return {"colonies": 0}

    step_x = across / max(1, columns - 1)
    step_y = across / max(1, rows - 1)

    # How solid each kind is inside its own outline. A branching colony's
    # extent is mostly gaps — you can see the sand through it — and counting its
    # bounding ellipse as covered ground overstates a staghorn thicket by about
    # three times. A boulder is nearly all boulder.
    # A gorgonian is nearly all hole — you can see the reef through a sea fan,
    # and counting its outline as covered ground would say a field of them was
    # a pavement.
    solidity = {"branching": 0.32, "fan": 0.14, "plume": 0.20, "sponge": 0.80,
                "finger": 0.55, "massive": 0.88, "brain": 0.90, "table": 0.80,
                "rubble": 0.62, "encrusting": 0.75,
                # A sea cucumber is a solid body with a smooth outline: what
                # it covers is very nearly the ellipse it lies in.
                "holothurian": 0.92}

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
             "brain": 0.62, "finger": 0.60, "rubble": 0.30,
             "encrusting": 0.34,
             # The gorgonians stand as tall as anything on the reef and are
             # most of its silhouette. A sea fan at eighty centimetres is a
             # seedling; a metre and a bit is an ordinary one.
             "fan": 1.15, "plume": 0.95, "sponge": 0.60,
             # The prototype's own scale, which for this one is a body
             # dimension rather than a colony's reach: `holothurian()` reads
             # it as the animal's girth and builds four or five of it in
             # length. Capped at its real length by NO_BIGGER_THAN_M.
             "holothurian": 0.11}
    # A table two metres across is a table; the same multiplier on a plate that
    # is already three metres wide gives a seven metre sheet, and a handful of
    # those fill the view and read as scenery flats.
    per_kind = {"branching": 1.0, "rubble": 1.0, "encrusting": 0.36,
                "finger": 1.0, "massive": 0.9, "table": 0.55,
                "brain": 0.9, "fan": 0.9, "plume": 0.9, "sponge": 0.9,
                # Small, and kept small by its own cap below rather than by
                # the band's: an animal's length is set by the animal.
                "holothurian": 0.30}

    bands = zonation.bands_for(assemblage)
    kinds = sorted({kind for mix in zonation.ASSEMBLAGES.values()
                    for _, weights, _ in mix for kind in weights})
    variants = 6

    # Which growth forms somebody has scanned. A scan carries the corallite
    # structure and the growth banding that no amount of noise on a blob
    # produces, and it is the difference between a colony and a painted stone.
    scans = scanned.found_in(reference) if reference is not None else {}
    # Two variants in three of a scanned form are scans, and each is a
    # different specimen; the rest are grown. One specimen is one colony that
    # happened to be collected, and a field of sixty identical boulders is as
    # wrong as a field of sixty blobs in a way that is harder to spot. The
    # grown ones stay because no museum has scanned the long tail.
    from_a_scan = 0

    prototypes, colours = [], []
    for kind in kinds:
        here = scans.get(kind, [])
        for at in range(variants):
            size = sizes[kind] * rng.uniform(0.7, 1.4)
            if here and at % 3 != 2:
                prototypes.append(
                    scanned.as_a_colony(here[from_a_scan % len(here)], size))
                from_a_scan += 1
            else:
                prototypes.append(coral.grow_one(kind, rng, size))
            colours.append(coral.a_colour(rng, kind))

    # Measured on what is above the seabed. A scan keeps its buried base, which
    # is wider than the colony that grows out of it; counting that as covered
    # ground would have the reef hit its cover target with fewer colonies than
    # the survey saw.
    footprint = np.zeros(len(prototypes))
    for i, (points, _) in enumerate(prototypes):
        if len(points):
            up = points[points[:, 2] >= 0.0]
            if len(up) < 3:
                up = points
            width = float(np.ptp(up[:, 0]))
            breadth = float(np.ptp(up[:, 1]))
            footprint[i] = (np.pi * (width / 2) * (breadth / 2)
                            * solidity[kinds[i // variants]])

    # Capped on how tall it stands, not how wide it is. A sea fan is a metre
    # and a half of height on a thirty centimetre footprint, and capping its
    # width lets it grow to three metres tall on a reef crest.
    widths = np.array([max(1e-3, float(points[:, 2].max()))
                       for points, _ in prototypes])
    # And how long each one lies, for the things a height cap does not cap.
    #
    # A sea cucumber is eight centimetres tall and half a metre long, so the
    # deep band's 1.8 m ceiling on height is no ceiling at all on it: the
    # first draw would have put five-times-life-size holothurians on the mud.
    # `zonation.NO_BIGGER_THAN_M` says what an animal's own size is, and this
    # is the measurement that cap applies to.
    lies = np.array([max(1e-3, float(max(np.ptp(points[:, 0]),
                                         np.ptp(points[:, 1]))))
                     for points, _ in prototypes])
    own_size = np.array([zonation.NO_BIGGER_THAN_M.get(kinds[i // variants], 0.0)
                         for i in range(len(prototypes))])
    kind_scale = np.array([per_kind[k] for k in kinds])

    def a_draw(at_depth, rng):
        """Which prototype each colony is, how big, and what it covers."""
        _, which_kind, cap = zonation.community(at_depth, rng, bands)
        which = which_kind * variants + rng.integers(0, variants, len(at_depth))
        scale = rng.uniform(0.65, 1.8, len(at_depth)) * kind_scale[which_kind]
        # No bigger than the band allows. A three metre table belongs on the
        # fore reef, not on a crest scoured to the rock every winter.
        scale = np.minimum(scale, cap / widths[which])
        # And no bigger than the animal itself gets, whatever band it is in.
        has_own = own_size[which] > 0
        if has_own.any():
            scale = np.where(
                has_own,
                np.minimum(scale, own_size[which] / lies[which]),
                scale)
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
    turn = rng.uniform(0, 2 * math.pi, how_many)

    # The surface of a coral at the scale of its polyps, and the material that
    # reads it. Both live with the place: a published package has to carry
    # everything it is drawn from.
    import shutil

    import corallite
    kinds_of = [kinds[i // variants] for i in range(len(prototypes))]
    for form in sorted({f for f in map(corallite_for, kinds_of) if f}):
        corallite.write(form, where / "textures")
    shutil.copy(pathlib.Path(__file__).resolve().parent.parent
                / "catalog" / "materials" / "coral_tissue.mdl",
                where / "coral_tissue.mdl")

    (where / "coral.usda").write_text(
        _instancer(prototypes, colours, kinds_of, x, y, z, which, scale, turn))

    # How much of the ground this actually covers.
    #
    # A single number over "the reef" is not a measurement, because it depends
    # entirely on how generously the reef is defined — a loose threshold makes a
    # dense reef look thin and a tight one saturates at a hundred per cent
    # whatever the count is. Both happened. What a diver means by cover is
    # local: stand somewhere on the reef, look down, and see how much of the
    # ground is coral.
    #
    # Worked out by `cover_over` above, which `tools/deliver` also calls on the
    # colonies it reads back out of the published USD. Two independent inputs,
    # one definition: if they disagree the file does not contain the reef this
    # function says it built. They used to disagree by up to half as much
    # again, and the reason was that there were two *definitions*.
    measured = cover_over(x, y, covered_by, across)
    cover = measured["cover"]
    thick = measured["thicketM2"]

    asked_for = float(np.average(want, weights=want > 0.02)) if (want > 0.02).any() else 0.0
    begin = zonation.best_ground(ground, want, across)
    return {"colonies": int(how_many), "prototypes": len(prototypes),
            # What each prototype *is*, by its index in the instancer, and how
            # much ground one of them covers at scale one.
            #
            # Said rather than left to be worked out. `tools/deliver` has to
            # put a growth form and a plan area on every colony in a CSV
            # somebody will open in a spreadsheet, and its first version
            # reverse-engineered both from the USD: it assumed the prototype
            # index was kind times variants plus variant, and it read the
            # kinds off `reef.kinds`, which on a surveyed place is a
            # *histogram* and not a list. Every row came out labelled "low" or
            # "unknown" and every footprint was a hundred times too small.
            #
            # A file that has to be reverse-engineered by the tool that ships
            # it is a file that will be reverse-engineered wrong.
            "prototypeKinds": [kinds[i // variants] for i in range(len(prototypes))],
            "prototypeAreaM2": [round(float(one), 6) for one in footprint],
            "variantsEach": variants,
            # Nothing here is a measurement. A colony's size is a draw against
            # a prototype's size, and a colony inventory out of this place
            # must not claim otherwise — which is the whole point of saying it
            # here rather than letting the exporter assume.
            "sizesAre": "grown",
            "sizesFrom": "a draw against the prototype's own size, capped by "
                         "the depth band; nobody measured any of these",
            # How many of the shapes came from a scan rather than a grower,
            # so a place's page can say what its coral is made of and nobody
            # has to take a render's word for it.
            "fromScans": from_a_scan,
            "scannedForms": sorted(scans),
            "cover": {
                "asked": round(asked_for, 5),
                # Five places, not three.
                #
                # `tools/deliver` measures this again off the published USD
                # and holds the two against each other to one per cent, and at
                # Thuwal Deep's three per cent cover the third decimal place
                # *is* one per cent: 0.0326 written as 0.033 failed the check
                # on its own rounding. A record whose precision is coarser
                # than the test it has to pass is a record that fails for no
                # reason, and the first instinct is to loosen the test.
                "whereItGrows": round(cover, 5),
                "perSquareKm": round(how_many / max(1e-9, (across / 1000) ** 2)),
                "from": cover_from,
                # Nothing that comes out of this function is measured. The
                # cover is worked out from the depth and the ground; only a
                # survey can say what is actually there, and a survey does not
                # come through here.
                "measured": False,
            },
            "coverAskedFor": round(asked_for, 5),
            "beginAt": begin,
            "points": int(sum(len(p) for p, _ in prototypes)),
            "coverWhereItGrows": round(cover, 5),
            "reefAreaM2": int(round(measured["reefGroundM2"])),
            "denseAreaM2": int(thick),
            # How it was measured, so a deliverable computing the same number
            # off the published file can be held against this one rather than
            # quietly reporting a different statistic under the same word.
            "coverMeasuredBy": {
                "cellM": measured["cellM"],
                "over": "cells with more than %g cover in them" % COVER_FLOOR,
                "statistic": "mean over those cells, each saturated as "
                             "1 - exp(-A/G) because colonies are scattered "
                             "rather than tiled",
                "medianCover": round(measured["medianCover"], 3),
                "piledUp": round(measured["piledUp"], 3),
                "colonyAreaM2": round(measured["colonyAreaM2"], 1),
                "biggerThanACell": measured["biggerThanACell"],
            }}


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


# How much of its own colour a colony emits.
#
# `UsdPreviewSurface` has no subsurface term, and coral is translucent tissue
# over a white aragonite skeleton: light goes in, scatters, and leaves nearby,
# which is why a living colony looks lit from inside and a dead one looks like
# a stone. A few per cent of its own colour, emitted, stands in for that.
#
# There is an MDL material now — catalog/materials/coral_tissue.mdl — and this
# is what is left for renderers that cannot read one. It is a cheat, and it is
# the honest cheat: the alternative for those renderers is a painted rock.
TISSUE_GLOW = 0.055

# Wet, not chalk. Roughness 0.82 is a dry bone; tissue under water is nearer a
# half, and the highlight that comes with it is most of what says "under water"
# rather than "on a shelf".
WET = 0.52

# How much tissue is on the skeleton. One is a healthy colony and nought is
# bare aragonite; a bleached reef is this number falling, which is a thing this
# platform should be able to show and cannot yet say a measured value for.
#
# What is left of the mix at 0.85 is fifteen per cent bare skeleton over the
# whole colony, and against a tissue colour of 0.26 that is enough grey to
# read as a washed-out colony rather than a living one.
ALIVE = 0.94

# And how much light goes right through, per growth form, because it is a
# property of the shape and not of coral.
#
# A branch tip and the edge of a plate pass light, and that lit rim is the
# first thing an eye uses to tell coral from rock. A boulder passes none: it
# is thirty centimetres of aragonite. Giving a boulder transmission on a closed
# mesh does not make it glow, it makes the bright sand behind it come through,
# and an olive colony rendered as a pale grey pebble — which is what the first
# pass did, and is the bleached look this material exists to stop.
# The names are both vocabularies: the growth forms tools/reef.py grows, and
# the kinds tools/benthos reports off a survey, which are what a photogrammetric
# DEM can actually distinguish.
THROUGH = {"massive": 0.0, "brain": 0.0, "encrusting": 0.05,
           "finger": 0.12, "branching": 0.30, "table": 0.35,
           "fan": 0.45, "plume": 0.40, "sponge": 0.10, "rubble": 0.0,
           # A holothurian is a bag of water and muscle several centimetres
           # thick. Nothing goes through it, and the thin-edge glow that makes
           # a sea fan read as tissue would make this read as jelly.
           "holothurian": 0.0,
           "low": 0.0, "stony": 0.0, "head": 0.0}
THROUGH_BY_DEFAULT = 0.0


# How much of the ground a reef covers, worked out one way for everybody.
#
# There were two of these and they disagreed by up to half as much again.
#
# `tools/reef.py` binned every colony into a *one metre* cell by its centre,
# summed the areas, kept the cells above two per cent and took the **median**,
# clipped at one. `tools/deliver` summed every colony's area, divided by the
# count of those cells and saturated it — a **mean**. Al Fahal came out 44.2%
# one way and 52.7% the other, Thuwal Deep 12.1% and 18.3%, and Red Sea the
# other way about. Nothing was broken: they were two different statistics of
# two different binnings wearing the same word.
#
# Both binnings also had the same fault under them. A cell one metre across is
# smaller than the colonies in it, so a three-metre table put seven square
# metres into a single cell and six of them were lost to the clip, while its
# neighbours — which it is physically standing over — got nothing.
#
# So: one function. A colony is spread over the cells it actually covers
# rather than dropped in the one its centre is in, as a square of the same
# area, which makes the overlap a product of two box intersections and exact
# to compute. Cells are five metres, which is larger than all but a handful of
# colonies and is about the resolution of the habitat maps these places are
# built against. Within a cell colonies are scattered rather than tiled, so
# what they cover is 1 - exp(-A/G) and not A/G — the same arithmetic the
# planting uses to decide how many to plant.
#
# What comes back is the mean over the ground that has any reef on it, which
# is what a diver means by "cover on this reef", and the median beside it,
# because the two differ exactly where a reef is patchy and that is worth
# seeing rather than choosing between.
COVER_CELL_M = 5.0
# Below this a cell is bare ground rather than thin reef. Two per cent of a
# five-metre cell is half a square metre.
COVER_FLOOR = 0.02
# And above this a cell is thicket rather than scattered heads — close enough
# together to be an obstacle rather than a thing to fly past.
COVER_THICKET = 0.45


def cover_over(x, y, area, across: float, cell_m: float = COVER_CELL_M) -> dict:
    """What a reef of these colonies covers, and over how much ground.

    `x` and `y` are metres from the middle of the site, `area` each colony's
    plan area in square metres. Everything is in metres and nothing here knows
    what a growth form is.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    area = np.asarray(area, dtype=float)
    n = max(1, int(round(float(across) / float(cell_m))))
    piled = np.zeros((n, n))
    if x.size == 0:
        return {"cellM": float(cell_m), "cells": int(piled.size),
                "reefGroundM2": 0.0, "cover": 0.0, "medianCover": 0.0,
                "piledUp": 0.0, "colonyAreaM2": 0.0, "biggerThanACell": 0}

    # A square of the same area, so the overlap with a cell is a product of
    # two one-dimensional intersections. A colony wider than a cell is
    # clamped — there are a handful on the biggest reefs and spreading one
    # further would need its real outline, which this does not have.
    side = np.sqrt(np.maximum(area, 0.0))
    too_big = int((side > cell_m).sum())
    side = np.minimum(side, cell_m)
    half = side / 2.0

    # Into the corner-origin frame the grid is indexed in.
    left = (x + across / 2.0) - half
    bottom = (y + across / 2.0) - half
    lo_c = np.floor(left / cell_m).astype(int)
    lo_r = np.floor(bottom / cell_m).astype(int)

    # At most two cells in each direction, because a side is never more than a
    # cell. `np.add.at` rather than `+=` because many colonies land in one cell
    # and buffered addition would keep only the last of them.
    for dc in (0, 1):
        column = lo_c + dc
        edge = column * cell_m
        wide = np.clip(np.minimum(left + side, edge + cell_m)
                       - np.maximum(left, edge), 0.0, None)
        for dr in (0, 1):
            row = lo_r + dr
            floor_edge = row * cell_m
            tall = np.clip(np.minimum(bottom + side, floor_edge + cell_m)
                           - np.maximum(bottom, floor_edge), 0.0, None)
            share = wide * tall
            inside = ((column >= 0) & (column < n) & (row >= 0) & (row < n)
                      & (share > 0))
            if inside.any():
                np.add.at(piled, (row[inside], column[inside]), share[inside])

    ground = float(cell_m) * float(cell_m)
    covered = 1.0 - np.exp(-piled / ground)
    reef = covered > COVER_FLOOR
    on_reef = covered[reef]
    return {
        "cellM": float(cell_m),
        "cells": int(piled.size),
        "reefGroundM2": float(reef.sum()) * ground,
        # And the part of it that is thicket rather than scattered heads. A
        # diver knows the difference and so does a vehicle: it is where a
        # colony is close enough to the next one to be an obstacle.
        "thicketM2": float((covered > COVER_THICKET).sum()) * ground,
        "cover": float(on_reef.mean()) if on_reef.size else 0.0,
        "medianCover": float(np.median(on_reef)) if on_reef.size else 0.0,
        "piledUp": (float(piled[reef].sum()) / (float(reef.sum()) * ground)
                    if reef.any() else 0.0),
        "colonyAreaM2": float(area.sum()),
        "biggerThanACell": too_big,
    }


def _skins(colours, kinds=None, tile_metres: float = 0.04) -> str:
    """A material per prototype.

    A mesh carrying only a display colour gets flat shading, and under a bright
    sun every colony comes out chalk-white — which is what the first reef looked
    like: correct shapes, correct places, and the colour of bone.

    Two materials, not one. `coral_tissue.mdl` is what a renderer that reads
    MDL gets: translucent tissue over white aragonite, light through the thin
    parts, corallites at polyp scale, and a stand-in for fluorescence. The
    preview surface beside it is what everything else gets, and it is the
    bleached version of the same colony, because a diffuse surface with a
    colour on it is exactly what a dead skeleton is.
    """
    skins = []
    for i, colour in enumerate(colours):
        kind = None if kinds is None else kinds[i]
        form = _CORALLITES.get(kind)
        corallites = ("" if form is None else
                      '                asset inputs:corallites = '
                      '@textures/corallite_%s_normal.png@\n'
                      '                float inputs:tile_metres = %.4f\n'
                      % (form, tile_metres))
        skins.append(
            '        def Material "Skin_%d"\n        {\n'
            "            token outputs:mdl:surface.connect = "
            "</Coral/Skins/Skin_%d/Tissue.outputs:out>\n"
            "            token outputs:surface.connect = "
            "</Coral/Skins/Skin_%d/Surface.outputs:surface>\n"
            '            def Shader "Tissue"\n            {\n'
            '                uniform token info:implementationSource = "sourceAsset"\n'
            "                uniform asset info:mdl:sourceAsset = @coral_tissue.mdl@\n"
            '                uniform token info:mdl:sourceAsset:subIdentifier = "coral_tissue"\n'
            "                color3f inputs:tissue = (%.3g, %.3g, %.3g)\n"
            "                float inputs:alive = %.3g\n"
            "                float inputs:through = %.3g\n"
            "                float inputs:wet = %.3g\n"
            # The water between this colony and the camera. The runtime sets
            # all four as a dive opens and moves `eye` as it flies; what is
            # written here is what a place looks like opened in something that
            # does not know to.
            "                float3 inputs:eye = (0, 0, 0)\n"
            "                color3f inputs:attenuation = (4, 17, 13)\n"
            "                color3f inputs:veiling = (0.24, 0.55, 0.45)\n"
            "                float inputs:veil = 0\n"
            # Declared so the runtime can find them: it sets the water on
            # every shader that has an `eye`, and skips any input the prim
            # does not already carry. Which is how the site width came to be
            # missing — the map lookup needs it to turn a world position into
            # the map's own square, the runtime knows it, and with nothing
            # here to write it into the material kept the thousand metres it
            # was compiled with. On Al Fahal, three kilometres across, every
            # colony read the map a long way outside its edges and came back
            # the colour of the clamp, which is black. Looe Key is a thousand
            # metres across and was right by coincidence.
            "                float inputs:site_across = 1000\n"
            "                asset inputs:caustics = @@\n"
            "                float inputs:caustics_across = 90\n"
            "                float inputs:caustics_strength = 0\n"
            "                float inputs:show_distance = 0\n"
            # The same map the seabed uses. Raw, because every texel is
            # already exp(-distance / length) and reading it as sRGB puts it
            # through a curve it has no business going through.
            "                asset inputs:swum_map = "
            "@textures/site_survives.png@ (colorSpace = \"raw\")\n"
            "%s"
            "                token outputs:out\n"
            "            }\n"
            '            def Shader "Surface"\n            {\n'
            '                uniform token info:id = "UsdPreviewSurface"\n'
            "                color3f inputs:diffuseColor = (%.3g, %.3g, %.3g)\n"
            "                color3f inputs:emissiveColor = (%.4g, %.4g, %.4g)\n"
            "                float inputs:roughness = %.3g\n"
            "                float inputs:metallic = 0\n"
            "                token outputs:surface\n"
            "            }\n        }\n" % (
                i, i, i, colour[0], colour[1], colour[2],
                ALIVE, THROUGH.get(kind, THROUGH_BY_DEFAULT), WET, corallites,
                colour[0], colour[1], colour[2],
                colour[0] * TISSUE_GLOW, colour[1] * TISSUE_GLOW,
                colour[2] * TISSUE_GLOW, WET))
    return '    def Scope "Skins"\n    {\n%s    }\n' % "".join(skins)


# Which corallite surface each kind wears. The octocorals are absent on
# purpose: a sea fan has no corallites at all, its surface is a mesh of
# spicules with polyps standing off it, and that is a different thing.
#
# "low" is a massive coral here and it is the least certain entry: tools/benthos
# calls a low grey lump "low" precisely because it cannot tell rock from
# Siderastrea. Corallites on rock is wrong; a smooth dome where there is a
# Siderastrea is also wrong, and of the two this one is wrong at a millimetre
# rather than at a metre.
_CORALLITES = {"massive": "massive", "brain": "brain", "branching": "branching",
               "table": "table", "encrusting": "encrusting", "finger": "finger",
               "low": "massive", "stony": "massive", "head": "brain"}


def corallite_for(kind):
    """The corallite surface a kind wears, or None where nobody has one."""
    return _CORALLITES.get(kind)


def _instancer(prototypes, colours, kinds_of, x, y, z, which, scale, turn) -> str:
    """The reef, as one instancer over a handful of grown prototypes."""
    grown = []
    for i, ((points, faces), colour) in enumerate(zip(prototypes, colours)):
        counts = ", ".join(["3"] * len(faces))
        indices = ", ".join(str(v) for v in faces.reshape(-1))
        grown.append(
            '\n        def Mesh "Coral_%d" (\n'
            '            prepend apiSchemas = ["MaterialBindingAPI"]\n'
            "        )\n        {\n"
            # Smoothed. The prototypes are low-poly on purpose and the facets
            # show on anything domed; subdividing costs nothing at render time.
            '            uniform token subdivisionScheme = "catmullClark"\n'
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
            _skins(colours, kinds_of),
            _triples(np.stack([x, y, z], axis=-1)),
            ", ".join(str(int(i)) for i in which),
            _triples(np.stack([scale, scale, scale], axis=-1)),
            ", ".join("(%.5g, %.5g, %.5g, %.5g)" % (w, a, b, c)
                      for w, a, b, c in orient),
            ", ".join("</Coral/Grown/Coral_%d>" % i for i in range(len(prototypes))),
            "".join(grown)))
