"""Fish, as things that are there rather than as scenery.

A reef without fish reads as a model of a reef. But the reason to do this
properly is not that it looks better: it is that a monitoring mission should be
**scorable on counting them**. A survey that flies a transect and reports
"forty-one fish, mostly parrotfish" is a survey whose autonomy can be judged.
Scenery cannot be counted, so scenery is not what this is.

So every fish here has a position, a species group, and a length, and the
runtime can be asked what is in front of a camera. What they do between frames
is a flocking model, which is the cheapest thing that produces behaviour an ROV
pilot recognises: schools that hold together, hold station over their own patch
of reef, and scatter when something comes at them and then reform.

**Where the numbers come from.** The groups, and how many of each, are the
observations recorded at the place itself — 2,440 of them at Looe Key over 114
species of bony fish. What each group *does* is from the literature on
Caribbean reef fish and is parameterised here with its reasoning written down,
because nobody has measured "how fast does a school reform" on this reef and
pretending otherwise would be worse than saying so.
"""

from __future__ import annotations

import numpy as np

# The behaviour groups, and what a fish of each does.
#
# Not species. There are 114 species of bony fish in the Looe Key record and
# they do about eight different things; a model with 114 sets of parameters
# would be 114 guesses rather than eight.
#
#   above       metres off the bottom the group holds, and how much it varies
#   school      how many travel together, low and high
#   cruise      metres a second, unhurried
#   dash        metres a second, when something frightens it
#   length      metres, nose to tail
#   home        metres it will stray from its patch before turning back
#   wary        metres at which a vehicle starts to matter
GROUPS = {
    # Grazers on the bottom, singly or in loose twos and threes. The most
    # abundant thing on this reef and the one a camera sees most.
    "parrotfish": dict(above=(0.6, 0.4), school=(1, 4), cruise=0.45, dash=1.6,
                       length=0.35, home=25.0, wary=4.0),
    # Hang in the water over the reef in tight schools, facing the current.
    "snapper": dict(above=(2.5, 1.2), school=(8, 40), cruise=0.35, dash=1.9,
                    length=0.30, home=18.0, wary=6.0),
    # Loose foraging groups that drift over the pavement.
    "surgeonfish": dict(above=(1.0, 0.6), school=(4, 18), cruise=0.40, dash=1.5,
                        length=0.25, home=22.0, wary=4.5),
    # Small, dense, and strongly tied to one head of coral.
    "damselfish": dict(above=(1.2, 0.8), school=(10, 60), cruise=0.30, dash=1.2,
                       length=0.09, home=6.0, wary=2.5),
    # Darting, close to the bottom, never still.
    "wrasse": dict(above=(0.5, 0.3), school=(1, 6), cruise=0.50, dash=1.4,
                   length=0.14, home=12.0, wary=3.0),
    # Pairs, slow, over coral. They are pairs for life and the model keeps
    # them in twos because a solitary butterflyfish is the unusual sight.
    "butterflyfish": dict(above=(0.8, 0.5), school=(2, 2), cruise=0.28, dash=1.1,
                          length=0.13, home=15.0, wary=3.5),
    # Fast, open water, passing through rather than living here.
    "jack": dict(above=(4.0, 2.5), school=(1, 8), cruise=0.9, dash=3.2,
                 length=0.45, home=120.0, wary=8.0),
    # Everything that is on its own: filefish, trumpetfish, grouper, hogfish.
    "solitary": dict(above=(1.0, 0.8), school=(1, 1), cruise=0.35, dash=1.5,
                     length=0.30, home=30.0, wary=5.0),
    # And everything that sits on the bottom rather than swimming over it:
    # gobies, blennies, sandperches, hawkfish perched on a coral head.
    #
    # This group exists because a Red Sea record said it should. Measuring how
    # much of Al Fahal's species list the map could place came back at 45%
    # unplaced and named the genera that did it, and half of them were fish
    # that do not swim in the water column at all. They are small, they barely
    # move, they hold a few centimetres off the substrate, and they let a
    # vehicle get very close before they go — which is the opposite of
    # everything else here and is most of what is actually on a reef.
    "bottom": dict(above=(0.08, 0.05), school=(1, 3), cruise=0.12, dash=0.9,
                   length=0.07, home=3.0, wary=1.2),
}

# Which genus belongs to which group. Genus, because the record names species
# and the behaviour is a property of the genus at this resolution.
#
# Both oceans. The first version of this was Caribbean only, which was fine
# while Looe Key was the only place with a record; the moment a Red Sea reef
# got one, every Pseudanthias, Pomacentrus and Chlorurus on it fell silently
# into "solitary" and a reef of schooling planktivores was drawn as a reef of
# loners. `as_observed` now reports how much of a record it could not place,
# so the next ocean says so instead of quietly looking wrong.
BY_GENUS = {
    # ── grazers on the bottom ────────────────────────────────────────────────
    "scarus": "parrotfish", "sparisoma": "parrotfish",
    "chlorurus": "parrotfish", "hipposcarus": "parrotfish",
    "calotomus": "parrotfish", "cetoscarus": "parrotfish",
    # ── schools hanging over the reef ────────────────────────────────────────
    "ocyurus": "snapper", "lutjanus": "snapper", "haemulon": "snapper",
    "anisotremus": "snapper", "macolor": "snapper", "plectorhinchus": "snapper",
    "caesio": "snapper", "pterocaesio": "snapper", "monotaxis": "snapper",
    # ── loose foraging groups ────────────────────────────────────────────────
    "acanthurus": "surgeonfish", "zebrasoma": "surgeonfish",
    "ctenochaetus": "surgeonfish", "naso": "surgeonfish",
    "siganus": "surgeonfish",
    # ── small, dense, tied to a head of coral ────────────────────────────────
    "abudefduf": "damselfish", "microspathodon": "damselfish",
    "azurina": "damselfish", "chromis": "damselfish", "stegastes": "damselfish",
    "pomacentrus": "damselfish", "pycnochromis": "damselfish",
    "dascyllus": "damselfish", "amphiprion": "damselfish",
    "neopomacentrus": "damselfish", "chrysiptera": "damselfish",
    # Anthias hover in their hundreds a metre or two over the reef and go back
    # into it when anything comes: small, dense and site-attached, which is
    # this group whatever the family says.
    "pseudanthias": "damselfish", "anthias": "damselfish",
    # ── darting, close to the bottom ─────────────────────────────────────────
    "thalassoma": "wrasse", "bodianus": "wrasse", "halichoeres": "wrasse",
    "lachnolaimus": "wrasse", "epibulus": "wrasse", "cheilinus": "wrasse",
    "coris": "wrasse", "labroides": "wrasse", "gomphosus": "wrasse",
    "cheilio": "wrasse", "hemigymnus": "wrasse",
    # ── pairs, slow, over coral ──────────────────────────────────────────────
    "chaetodon": "butterflyfish", "holacanthus": "butterflyfish",
    "pomacanthus": "butterflyfish", "pygoplites": "butterflyfish",
    "heniochus": "butterflyfish", "genicanthus": "butterflyfish",
    "chaetodontoplus": "butterflyfish",
    # ── fast, open water, passing through ────────────────────────────────────
    "caranx": "jack", "sphyraena": "jack", "seriola": "jack",
    "elagatis": "jack", "gnathanodon": "jack", "scomberoides": "jack",
    # ── sitting on the bottom, not swimming over it ──────────────────────────
    "eviota": "bottom", "amblyeleotris": "bottom", "valenciennea": "bottom",
    "istigobius": "bottom", "ecsenius": "bottom", "parapercis": "bottom",
    "paracirrhites": "bottom", "cirrhitichthys": "bottom",
    "gobiodon": "bottom", "pseudochromis": "bottom", "meiacanthus": "bottom",
    "salarias": "bottom", "synodus": "bottom", "corythoichthys": "bottom",
    # ── on their own: groupers, squirrelfish, triggers, filefish, puffers ────
    "cephalopholis": "solitary", "epinephelus": "solitary",
    "plectropomus": "solitary", "variola": "solitary",
    "sargocentron": "solitary", "myripristis": "solitary",
    "balistoides": "solitary", "rhinecanthus": "solitary",
    "balistapus": "solitary", "melichthys": "solitary",
    "aluterus": "solitary", "aulostomus": "solitary", "fistularia": "solitary",
    "arothron": "solitary", "diodon": "solitary", "ostracion": "solitary",
    "zanclus": "solitary", "platax": "solitary",
    # ── mid-water schools: emperors and fusiliers are the Indo-Pacific grunts
    "lethrinus": "snapper", "gnathodentex": "snapper",
    "amblyglyphidodon": "damselfish", "dischistodus": "damselfish",
    # ── and the tail each record named when it was measured ──────────────────
    # Al Fahal's, then Looe Key's. Both lists came out of
    # `how_much_was_placed`, which is the point of having it: it does not say
    # "some of this is unplaced", it says which genera and how many.
    "trimma": "bottom", "vanderhorstia": "bottom", "ctenogobiops": "bottom",
    "gymnothorax": "bottom", "ophioblennius": "bottom",
    "brachygenys": "snapper", "calamus": "snapper",
    "holocentrus": "solitary", "scomberomorus": "jack",
}
OTHERWISE = "solitary"


def group_of(taxon: str) -> str:
    """Which behaviour group a species name belongs to."""
    return BY_GENUS.get(taxon.split()[0].lower(), OTHERWISE)


def how_much_was_placed(counted) -> dict:
    """How much of a record this map could actually place, and what it could not.

    A record from an ocean this map does not know comes back almost entirely
    as "solitary", and a reef of schooling fish gets drawn as a reef of
    loners with nothing anywhere saying so. So: the share that landed in the
    fallback, and the genera that put it there, biggest first.
    """
    placed, fell_through = 0, {}
    for one in counted:
        if one.get("group") != "Actinopterygii":
            continue
        many = int(one.get("observations", 0))
        genus = one["taxon"].split()[0].lower()
        if genus in BY_GENUS:
            placed += many
        else:
            fell_through[genus] = fell_through.get(genus, 0) + many
    unplaced = sum(fell_through.values())
    total = placed + unplaced
    return {
        "observations": total,
        "placed": placed,
        "unplaced": unplaced,
        "unplacedShare": round(unplaced / total, 3) if total else 0.0,
        "commonestUnplaced": [g for g, _ in sorted(
            fell_through.items(), key=lambda kv: -kv[1])[:8]],
    }


def as_observed(counted, how_many: int) -> dict:
    """How many of each group to put on a reef, from what was seen there.

    `counted` is the place's own species list with its observation counts. The
    shares are what somebody actually saw; `how_many` is how many fish the reef
    is being asked to hold, which is a separate question and not one this
    record can answer — an observation count is a count of photographs, not a
    density.
    """
    seen: dict[str, int] = {}
    for one in counted:
        if one.get("group") != "Actinopterygii":
            continue
        seen[group_of(one["taxon"])] = (seen.get(group_of(one["taxon"]), 0)
                                        + int(one.get("observations", 0)))
    total = sum(seen.values())
    if total <= 0:
        return {}
    # Largest remainder, so the shares add to exactly what was asked for and
    # the smallest group is not rounded out of existence.
    exact = {k: how_many * v / total for k, v in seen.items()}
    whole = {k: int(v) for k, v in exact.items()}
    for name, _ in sorted(exact.items(), key=lambda kv: kv[1] - int(kv[1]),
                          reverse=True)[:how_many - sum(whole.values())]:
        whole[name] += 1
    return {k: v for k, v in whole.items() if v}


class Shoal:
    """Every fish on a reef, stepped together.

    One array of positions and one of velocities, not an object per fish: a
    reef holds a couple of thousand of them and they are stepped on the same
    clock as the physics. Everything below is vectorised over all of them at
    once for that reason, which is also why it reads as arithmetic rather than
    as behaviour.

    The behaviour is a flocking model — separation, alignment, cohesion — with
    three things added that a plain flock does not have and a reef fish does:

      **It holds station.** Reef fish live on a patch and come back to it.
      A flock with no home wanders off the site inside a minute.
      **It holds a depth.** A grazer stays near the bottom and a jack does
      not, and that is most of what tells them apart in a frame.
      **It scatters.** Something comes at it, it goes the other way fast, and
      then it comes back. That is the part an ROV pilot recognises instantly,
      and it is the reason this is a simulation of fish rather than a picture
      of them.
    """

    # How hard each urge pulls, relative to the others. Tuned by eye against
    # footage and not measured, which is the honest thing to say about it:
    # nobody has published the cohesion coefficient of a bluehead wrasse.
    APART = 1.4          # do not touch the fish beside you
    TOGETHER = 0.35      # stay with the school
    ALIGNED = 0.55       # go where the school is going
    HOME = 0.5           # and stay over your own patch
    DEPTH = 1.2          # at your own height off the bottom
    FLEE = 3.0           # and get out of the way

    # How close is too close, in body lengths. A school is dense; a metre of
    # separation between bluehead wrasse would be a school of nothing.
    ELBOW = 2.5

    def __init__(self, groups: dict, floor_at, across: float,
                 water_level: float = 0.0, seed: int = 0, about=(0.0, 0.0)) -> None:
        self.rng = np.random.default_rng(seed)
        self.floor_at = floor_at
        self.across = float(across)
        self.water_level = float(water_level)
        # Where the middle of the stocked water is, in the site's own
        # coordinates. A shoal is a patch of reef around the work and not the
        # whole site, and it has to know where that patch is: the first
        # version put the fish in their own square centred on nothing and then
        # slid them across afterwards, which left every lookup and every edge
        # measuring from the wrong place. They were clipped back off the dive
        # on the first step.
        self.about = np.array([float(about[0]), float(about[1])])

        kinds, home, above, school = [], [], [], []
        schools = 0
        for name, many in sorted(groups.items()):
            if name not in GROUPS:
                continue
            says = GROUPS[name]
            low, high = says["school"]
            put = 0
            while put < many:
                # One school at a time, each with its own patch of reef.
                size = min(int(self.rng.integers(low, high + 1)), many - put)
                at = self.about + self.rng.uniform(
                    -0.45 * across, 0.45 * across, 2)
                held = max(0.2, self.rng.normal(*says["above"]))
                for _ in range(size):
                    kinds.append(name)
                    home.append(at)
                    above.append(held)
                    # Which school this one is in. A kind is spread over the
                    # whole reef in a dozen separate schools; the school is the
                    # thing that holds together, and without this there is no
                    # way to ask whether it did.
                    school.append(schools)
                schools += 1
                put += size

        self.kinds = np.array(kinds)
        self.school = np.array(school, dtype=int)
        self.home = np.array(home, dtype="float64") if home else np.zeros((0, 2))
        self.above = np.array(above, dtype="float64")
        self.of_them = len(self.kinds)

        # The per-fish constants, unpacked once so the step does no lookups.
        #
        # `home` is the group's roaming range and is deliberately not called
        # that here: `self.home` is already where each fish lives, and the
        # first version of this loop wrote the ranges straight over the
        # positions. Every fish on the reef then had its home at (25, 25).
        for field in ("cruise", "dash", "length", "wary"):
            setattr(self, field, np.array(
                [GROUPS[k][field] for k in self.kinds], dtype="float64"))
        self.roam = np.array([GROUPS[k]["home"] for k in self.kinds],
                             dtype="float64")

        self._remember_the_floor()
        self.at = np.zeros((self.of_them, 3))
        if self.of_them:
            self.at[:, :2] = self.home + self.rng.normal(0, 2.0, (self.of_them, 2))
            self.at[:, 2] = self._floor(self.at[:, :2]) + self.above
        # Which fish are which kind, worked out once: the step needs it every
        # tick and `self.kinds == k` over two thousand strings is not free.
        self._kinds_present = sorted(set(self.kinds.tolist()))
        self._of_kind = {k: np.flatnonzero(self.kinds == k)
                         for k in self._kinds_present}
        self.going = self.rng.normal(0, 0.2, (self.of_them, 3))
        self.going[:, 2] *= 0.2
        self.scattered = 0.0

    # How finely the seabed is remembered, for asking where the bottom is.
    #
    # Asking the place itself is a Python call per fish per step, and two
    # thousand fish at twenty steps a second is eighty thousand calls a second
    # for a number that does not change. Sampled once into a grid and read off
    # it, which for a fish holding a metre off the bottom is exactly as good.
    REMEMBERED = 192

    def _remember_the_floor(self):
        n = self.REMEMBERED
        edge = 0.5 * self.across
        line_x = np.linspace(self.about[0] - edge, self.about[0] + edge, n)
        line = np.linspace(self.about[1] - edge, self.about[1] + edge, n)
        self._known = np.empty((n, n))
        for j, y in enumerate(line):
            for i, x in enumerate(line_x):
                got = self.floor_at(float(x), float(y))
                self._known[j, i] = -30.0 if got is None else float(got)
        self._known_at = line

    def _floor(self, xy):
        """The seabed under each of them, as an array."""
        n = self.REMEMBERED
        edge = 0.5 * self.across
        where = (np.asarray(xy) - self.about + edge) / (2 * edge) * (n - 1)
        where = np.clip(where, 0, n - 1.001)
        i, j = where[:, 0].astype(int), where[:, 1].astype(int)
        fx, fy = where[:, 0] - i, where[:, 1] - j
        known = self._known
        return ((known[j, i] * (1 - fx) + known[j, i + 1] * fx) * (1 - fy)
                + (known[j + 1, i] * (1 - fx) + known[j + 1, i + 1] * fx) * fy)

    def step(self, dt: float, vehicle=None, thrust: float = 0.0) -> None:
        """One tick of the whole reef.

        `thrust` is how hard the vehicle is working, which is what actually
        frightens a fish: a vehicle drifting past on a current is a log, and
        the same vehicle on full thrusters clears a hundred square metres.
        """
        if not self.of_them or dt <= 0:
            return
        want = np.zeros_like(self.going)

        # ── the school ───────────────────────────────────────────────────────
        # A kind at a time. A wrasse does not school with a barracuda, so the
        # whole-reef distance matrix was computing four million distances to
        # throw away seven eighths of them; eight small matrices are the same
        # answer and, at two thousand fish, eight times less of it.
        for kind in self._kinds_present:
            these = self._of_kind[kind]
            if len(these) < 2:
                continue
            at, going = self.at[these], self.going[these]
            gap = at[:, None, :] - at[None, :, :]
            far = np.linalg.norm(gap, axis=2)
            np.fill_diagonal(far, np.inf)

            elbow = self.ELBOW * GROUPS[kind]["length"]
            crowded = far < elbow
            with np.errstate(invalid="ignore", divide="ignore"):
                push = np.where(crowded[:, :, None],
                                gap / far[:, :, None] ** 2, 0.0)
            want[these] += self.APART * np.nan_to_num(push).sum(axis=1)

            near = far < 6.0
            many = near.sum(axis=1)
            held = np.maximum(many, 1)[:, None]
            middle = np.where(many[:, None] > 0, near @ at / held, at)
            theirs = np.where(many[:, None] > 0, near @ going / held, going)
            want[these] += self.TOGETHER * (middle - at)
            want[these] += self.ALIGNED * (theirs - going)

        # ── its own patch, and its own height over it ────────────────────────
        adrift = self.at[:, :2] - self.home
        out = np.linalg.norm(adrift, axis=1)
        pull = np.where(out > self.roam, (out - self.roam) / self.roam, 0.0)
        want[:, :2] -= self.HOME * pull[:, None] * adrift

        floor = self._floor(self.at[:, :2])
        wants_z = np.minimum(floor + self.above, self.water_level - 0.5)
        want[:, 2] += self.DEPTH * (wants_z - self.at[:, 2])

        # ── and the thing coming at it ───────────────────────────────────────
        if vehicle is not None:
            off = self.at - np.asarray(vehicle, dtype="float64")[None, :]
            how_far = np.linalg.norm(off, axis=1)
            # A working vehicle frightens fish further away than a drifting
            # one. Half again at full thrust, which is a guess with a shape
            # rather than a measurement.
            reach = self.wary * (1.0 + 0.5 * min(1.0, max(0.0, thrust)))
            afraid = how_far < reach
            if afraid.any():
                with np.errstate(invalid="ignore", divide="ignore"):
                    away = np.where(afraid[:, None],
                                    off / np.maximum(how_far, 0.05)[:, None]
                                    * ((reach - how_far) / reach)[:, None], 0.0)
                want += self.FLEE * np.nan_to_num(away)
            self.scattered = float(afraid.mean())
        else:
            self.scattered = 0.0

        # ── and what that comes to ───────────────────────────────────────────
        self.going += want * dt
        # A frightened fish can dash; an unfrightened one cruises. This is the
        # whole of the speed model and it is enough: what reads as alarm in a
        # frame is the change of speed, not the absolute value.
        hurry = self.cruise + (self.dash - self.cruise) * (
            np.linalg.norm(want, axis=1) > 2.0)
        speed = np.linalg.norm(self.going, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.going = np.where(
                (speed > hurry)[:, None],
                self.going * (hurry / np.maximum(speed, 1e-9))[:, None],
                self.going)
        self.at = self.at + self.going * dt

        # Never inside the ground, and never out of the water.
        floor = self._floor(self.at[:, :2])
        self.at[:, 2] = np.clip(self.at[:, 2], floor + 0.08, self.water_level - 0.3)
        edge = 0.49 * self.across
        self.at[:, :2] = np.clip(self.at[:, :2], self.about - edge,
                                 self.about + edge)

    def seen_from(self, at, looking, half_angle_deg: float = 32.0,
                  reach: float = 12.0) -> dict:
        """What a camera at `at` pointing along `looking` would have in frame.

        This is the reason the fish are simulated rather than drawn: a dive
        that counts fish can be scored against what was actually there, which
        is a thing the platform knows and the autonomy does not.
        """
        if not self.of_them:
            return {}
        off = self.at - np.asarray(at, dtype="float64")[None, :]
        how_far = np.linalg.norm(off, axis=1)
        way = np.asarray(looking, dtype="float64")
        way = way / max(float(np.linalg.norm(way)), 1e-9)
        with np.errstate(invalid="ignore", divide="ignore"):
            facing = (off @ way) / np.maximum(how_far, 1e-9)
        inside = (how_far < reach) & (facing > np.cos(np.radians(half_angle_deg)))
        counted: dict[str, int] = {}
        for kind in np.unique(self.kinds[inside]):
            counted[str(kind)] = int((self.kinds[inside] == kind).sum())
        return counted

    def said(self) -> dict:
        """What is on this reef, for the record."""
        counted = {str(k): int((self.kinds == k).sum())
                   for k in np.unique(self.kinds)} if self.of_them else {}
        return {"fish": int(self.of_them), "byGroup": counted,
                "schools": int(len(np.unique(self.school))) if self.of_them else 0,
                "scattered": round(self.scattered, 3)}


# ── and what a renderer draws ────────────────────────────────────────────────

def put_them_in(stage, shoal, at: str = "/World/Life") -> None:
    """Write the shoal into the stage as one instancer, once.

    One prototype per behaviour group, which is one shape and one colour each.
    Not one per fish: a couple of thousand meshes is a couple of thousand prims
    for the renderer to think about every frame, and the whole reason a reef is
    a point instancer is that it is not that.
    """
    import numpy as np
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    from coral import fishform

    if not shoal.of_them:
        return
    rng = np.random.default_rng(7)
    instancer = UsdGeom.PointInstancer.Define(stage, at)
    looks = UsdGeom.Scope.Define(stage, f"{at}/Looks")
    shapes = UsdGeom.Scope.Define(stage, f"{at}/Bodies")

    prototypes = []
    for i, kind in enumerate(shoal._kinds_present):
        points, faces = fishform.body(fishform.OF_GROUP[kind])
        mesh = UsdGeom.Mesh.Define(stage, f"{shapes.GetPath()}/Fish_{i}")
        # `float(...)` on every component, and it is not decoration.
        #
        # `Gf.Vec3f(*row)` on a numpy array hands the binding three
        # numpy.float32, and the binding takes Python floats: it raises
        # "did not match C++ signature", which is a sentence about a type
        # nobody wrote down. Everything above this line is numpy because the
        # geometry is arithmetic; everything below is USD, and the boundary is
        # here.
        mesh.CreatePointsAttr(Vt.Vec3fArray(
            [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in points]))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
        mesh.CreateFaceVertexIndicesAttr(
            Vt.IntArray([int(v) for f in faces for v in f]))
        low, high = points.min(axis=0), points.max(axis=0)
        mesh.CreateExtentAttr([Gf.Vec3f(*(float(v) for v in low)),
                               Gf.Vec3f(*(float(v) for v in high))])
        # Both sides. The fins are single triangles and a one-sided fin is
        # invisible from half the reef.
        mesh.CreateDoubleSidedAttr(True)

        colour = fishform.a_colour(kind, rng)
        material = UsdShade.Material.Define(stage, f"{looks.GetPath()}/Fish_{i}")
        shader = UsdShade.Shader.Define(stage, f"{looks.GetPath()}/Fish_{i}/S")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*(float(c) for c in colour)))
        # Wet, and a fish is wetter than a rock: the flank of a live fish is
        # the brightest specular on a reef and it is most of how one catches
        # an eye at ten metres.
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.24)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
        prototypes.append(mesh.GetPath())

    instancer.CreatePrototypesRel().SetTargets(prototypes)
    instancer.CreateProtoIndicesAttr(Vt.IntArray(
        [shoal._kinds_present.index(k) for k in shoal.kinds]))
    # A fish is the length its group is, and they are not all the same size.
    size = np.array([GROUPS[k]["length"] for k in shoal.kinds])
    size = size * rng.uniform(0.72, 1.3, len(size))
    instancer.CreateScalesAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(s), float(s), float(s)) for s in size]))
    move_them(stage, shoal, at)


def move_them(stage, shoal, at: str = "/World/Life") -> None:
    """Put every fish where it is now, and face it where it is going."""
    from pxr import Gf, UsdGeom, Vt

    from coral import fishform

    if not shoal.of_them:
        return
    instancer = UsdGeom.PointInstancer.Get(stage, at)
    if not instancer:
        return
    instancer.CreatePositionsAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in shoal.at]))
    instancer.CreateOrientationsAttr(Vt.QuathArray(
        [Gf.Quath(*(float(c) for c in fishform.facing(v)))
         for v in shoal.going]))


# ── and the things that are rooted ───────────────────────────────────────────
#
# A sea fan is an animal and it is also a sail. It stands across the flow —
# which is why they all lie in the same plane on a reef, and why a still one
# looks stuffed. What moves it is not the mean current but the surge: the
# orbital motion of the waves overhead, which reverses every few seconds, and
# which this platform already computes because it acts on the vehicle too.

# How far a gorgonian leans, in radians, per metre a second of water. A sea fan
# in a half-knot of surge leans about fifteen degrees and comes back; this is
# that, and it is a number read off footage rather than measured.
LEAN = 0.55
# And how far a stiff one leans. A sea rod is a stick and a sea fan is a net.
STIFFNESS = {"fan": 1.0, "plume": 0.75}
# Nothing bends past this, whatever the water does. A gorgonian laid flat is a
# gorgonian that has been torn off.
MOST = 0.7


def bending(flow, phase, stiffness=1.0):
    """How far each rooted colony leans, and which way.

    `flow` is the water moving past, in metres a second, as (east, north).
    `phase` is a number per colony, so that a field of them does not move as
    one sheet: real ones are in each other's wake and no two are in step.

    Returns the lean in radians and the direction it leans, both as arrays.
    """
    east, north = float(flow[0]), float(flow[1])
    speed = np.hypot(east, north)
    if speed < 1e-6:
        return np.zeros_like(phase), np.zeros_like(phase)
    # Each one a little ahead of or behind the water, which is what makes a
    # field of them look like a field rather than a flag.
    lag = 1.0 + 0.25 * np.sin(phase)
    lean = np.minimum(MOST, LEAN * speed * stiffness * lag)
    return lean, np.full_like(phase, np.arctan2(north, east))


def leaning(lean, towards, turn):
    """The orientation of a colony that is rooted and leaning.

    Its own turn about the vertical, then a tilt away from upright in the
    direction the water is going. Quaternions, in the order a renderer wants
    them: w first.
    """
    # Tilt about the axis perpendicular to the flow, which is what bending
    # downstream is.
    axis_x, axis_y = -np.sin(towards), np.cos(towards)
    ch, sh = np.cos(lean / 2), np.sin(lean / 2)
    tw, tx, ty = ch, sh * axis_x, sh * axis_y

    cz, sz = np.cos(turn / 2), np.sin(turn / 2)
    # Tilt composed with the colony's own turn about z.
    return (tw * cz, tx * cz + ty * sz, ty * cz - tx * sz, tw * sz)
