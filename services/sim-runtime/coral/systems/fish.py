"""The fish: every one in the place, each with a mind (fishmind.py).

Reads    light, the water and the wash, the vehicle and its thrust, the place,
         the coral (which the fish swim round)
Writes   fish: the school — where each fish is, what it is doing, and why
Every    a twentieth of a second of simulated time

What they live in is the dive's water, so they are in every dive, drawn or
not: a fish count scored against a headless run is scored against fish that
were there. Each step they are handed the light from the day, the water's
motion where each of them is — the current and the vehicle's own wash — and
the vehicle: where it is, how big, and how hard it is working.

`stock` works out who lives where from the place's record: a tank says how
many of each it holds; a reef says what share of its fish each group is, and
how many to the square metre. Their homes are the place's own refuges: a
branching coral for a chromis, a crevice in the rock for a parrotfish, a
burrow in the sand for a goby.
"""

from __future__ import annotations

import numpy as np

from engine import System

# How far from where a dive begins the reef's fish are put. Not the whole
# site: a kilometre of seabed at the density a reef holds is tens of thousands
# of fish, more than can be drawn and more than a vehicle working one patch
# will meet. The record says which water was stocked.
STOCKED_TO_M = 90.0
MOST_FISH = 1400

# Coral growth forms, as the refuge each makes. Soft corals and sea fans hold
# no fish inside them; a clownfish's host anemone is a soft thing too, and in
# a tank that has none the plume coral stands for it.
REFUGE_OF = {"branching": "branch", "finger": "branch", "table": "branch",
             "massive": "crevice", "brain": "crevice", "sponge": "crevice",
             "plume": "host"}


class FishSystem(System):
    """Steps the school, and counts what the vehicle's camera sees of it.

    The count is the point of simulating the fish at all: a survey that
    counts fish is judged against how many were there, and a vehicle that
    frightens fish off counts fewer than were there. A fish is counted when it
    is inside the camera's field of view and near enough to tell what it is —
    half of how far the camera can see through the water, sediment included,
    and never more than five metres (assumed). Each fish once, however long it
    stays in view: `counted` is what a person counting the video would get.

    `blind` is the counterfactual: the same dive, with fish that do not see
    the vehicle. What the camera counts then, against what it counts when they
    do, is how much the vehicle's own presence cost the count
    (tools/count-bias)."""

    name = "fish"
    reads = ("light", "water", "wash", "flow", "vehicle", "thrust", "place", "clock", "sediment", "coral")
    writes = ("fish",)
    every = 0.05

    IDENTIFIED_WITHIN_M = 5.0

    def __init__(self, camera=None, blind: bool = False) -> None:
        # (where on the hull, pitch down in radians, half the field of view)
        self.camera = camera
        self.blind = bool(blind)
        self._coral_as = None

    def step(self, world) -> None:
        school = world.fish
        if school is None:
            return
        self.know_the_coral(school, world.coral)
        v = world.vehicle
        flow = world.water.flow_at(school.at, world.clock.simulated) + world.wash.at(school.at)
        working = (float(np.clip(np.abs(v.wrench[:3]).sum() / 60.0, 0.0, 1.0))
                   if v.wrench is not None else 0.0)
        school.step(self.every, vehicle=None if self.blind else v.position, thrust=working,
                    light=(world.light.hour, world.light.level), flow=flow,
                    vehicle_size=float(v.half_width))
        if self.camera is not None:
            self.count(school, v, world.sediment)

    def count(self, school, v, sediment) -> None:
        at, pitch, half = self.camera
        eye = v.position + v.rotation @ np.asarray(at, dtype=float)
        looking = v.rotation @ np.array([np.cos(pitch), 0.0, -np.sin(pitch)])
        seeing = self.IDENTIFIED_WITHIN_M
        if sediment.visibility_m is not None:
            seeing = min(seeing, 0.5 * float(sediment.visibility_m))
        off = school.at - eye[None, :]
        far = np.linalg.norm(off, axis=1)
        facing = (off @ looking) / np.maximum(far, 1e-9)
        seen = np.flatnonzero((far < seeing) & (facing > np.cos(half)))
        school.counted.update(int(i) for i in seen)
        school.in_view.append(len(seen))


    def know_the_coral(self, school, coral) -> None:
        """Tell the fish where the coral stands, so they go round it; and
        again round a colony broken or torn off, and nowhere else."""
        if self._coral_as is None or len(self._coral_as[0]) != len(coral):
            school.habitat.set_coral(*standing(coral))
            self._coral_as = (coral.height.copy(), coral.torn_off.copy())
            return
        height, torn = self._coral_as
        changed = np.flatnonzero((coral.height != height) | (coral.torn_off != torn))
        if not len(changed):
            return
        reach = float(coral.radius[changed].max())
        low = coral.at[changed, :2].min(axis=0) - reach
        high = coral.at[changed, :2].max(axis=0) + reach
        school.habitat.clear(low, high)
        near = coral.near(np.vstack([low, high]), 0.0)
        school.habitat.stamp(*standing(coral, near))
        self._coral_as = (coral.height.copy(), coral.torn_off.copy())


def standing(coral, which=None):
    """Where the colonies still standing are, how wide, and how high they
    reach: what a fish swims round."""
    which = np.arange(len(coral)) if which is None else np.asarray(which, dtype=int)
    which = which[~coral.torn_off[which]]
    return coral.at[which], coral.radius[which], coral.at[which, 2] + coral.height[which]


# A reef drawn as a layer has tens of thousands of colonies; this many of them,
# nearest first, are enough places to hide for the fish that are stocked.
MOST_REFUGES = 4000


def refuges(described: dict, bottom_under, low, high, rng, coral=None) -> dict:
    """The place's hiding places, by kind: from its coral colonies and its
    rocks, and burrows in the open sand between them."""
    found: dict[str, list] = {}
    listed = (described.get("reef") or {}).get("colonies_at") or []
    if not listed and coral is not None and len(coral):
        # The colonies of a reef layer (systems/coral.py), in the stocked water.
        middle = 0.5 * (np.asarray(low, dtype=float) + np.asarray(high, dtype=float))
        near = coral.near(middle, float(np.max(np.asarray(high) - middle)))
        near = near[np.argsort(np.linalg.norm(coral.at[near, :2] - middle, axis=1))][:MOST_REFUGES]
        listed = [{"kind": str(coral.kind[i]), "at": coral.at[i, :2].tolist(), "sizeM": float(coral.height[i])}
                  for i in near]
    for colony in listed:
        kind = REFUGE_OF.get(str(colony.get("kind")))
        at = colony.get("at")
        if kind is None or not at:
            continue
        x, y = float(at[0]), float(at[1])
        # Inside the colony, half its height up: where a damselfish sleeps.
        found.setdefault(kind, []).append((x, y, bottom_under(x, y) + 0.5 * float(colony.get("sizeM", 0.1))))
    for rock in described.get("rocks") or []:
        x, y = float(rock["at"][0]), float(rock["at"][1])
        r = float(rock.get("radiusM", 0.1))
        # The foot of a rock, where its crevices are.
        for a in np.linspace(0, 2 * np.pi, 4, endpoint=False):
            cx, cy = x + 0.9 * r * np.cos(a), y + 0.9 * r * np.sin(a)
            found.setdefault("crevice", []).append((cx, cy, bottom_under(cx, cy) + 0.02))
    # Burrows: open sand, which is the low ground.
    tries = rng.uniform(low, high, (400, 2))
    floors = np.array([bottom_under(float(x), float(y)) for x, y in tries])
    sand = tries[floors <= np.percentile(floors, 25) + 0.01]
    for x, y in sand[:40]:
        found.setdefault("burrow", []).append((float(x), float(y), bottom_under(float(x), float(y))))
    return {k: np.array(v, dtype=float) for k, v in found.items()}


def stock(described: dict, bottom_under, interior, begins_at, seed: int, say, light=None, coral=None,
          counted=None):
    """The school a place holds, or None, and says which."""
    import fishmind

    says = described.get("life") or {}
    rng = np.random.default_rng(seed + 7)
    if says.get("tank"):
        counts = {str(k): int(v) for k, v in (says.get("count") or {}).items() if int(v) > 0}
        if not counts:
            say("no_life", why="the tank says it holds no fish")
            return None
        if interior is not None:
            lo, hi = np.asarray(interior[0], dtype=float), np.asarray(interior[1], dtype=float)
        else:
            lo, hi = np.array([-0.5, -0.5, -1.0]), np.array([0.5, 0.5, 0.0])
        about = (lo[:2] + hi[:2]) / 2.0
        half = (hi[:2] - lo[:2]) / 2.0
        across = float(max(hi[0] - lo[0], hi[1] - lo[1]))
        circle = getattr(interior, "round", None)
        habitat = fishmind.Habitat(bottom_under, about, across, water_level=float(hi[2]),
                                   box=0.92 * half, circle=None if circle is None else
                                   (circle[0], circle[1], 0.96 * circle[2]),
                                   refuges=refuges(described, bottom_under,
                                                                    about - 0.9 * half, about + 0.9 * half, rng,
                                                                    coral),
                                   scale=float(says.get("scale", 1.0)))
        if coral is not None and len(coral):
            habitat.set_coral(*standing(coral))
        school = fishmind.School(counts, habitat, seed=seed, tank=True)
        if light is not None:
            school.hour, school.light = light
        say("life_is", **school.said(), refuges={k: len(v) for k, v in habitat.refuges.items()},
            stockedToM=round(across / 2, 2), asked=sum(counts.values()), drawn=school.of_them, tank=True)
        return school
    if not says.get("shares"):
        say("no_life", why="this place has no record of what lives in it")
        return None
    reef = np.pi * STOCKED_TO_M ** 2
    # Only the part that is reef rather than sand: the place's habitat share,
    # or half, which is the honest guess and written down as one.
    holds = float((described.get("reef") or {}).get("reefFraction", 0.5))
    wanted = int(reef * holds * float(says.get("perSquareMetre", 0.1)))
    how_many = min(MOST_FISH, wanted)
    groups, left = {}, how_many
    shares = sorted(says["shares"].items())
    for i, (name, share) in enumerate(shares):
        take = left if i == len(shares) - 1 else int(round(how_many * float(share)))
        groups[name] = max(0, min(left, take))
        left -= groups[name]
    about = np.asarray(begins_at, dtype=float)[:2]
    span = np.array([0.45, 0.45]) * 2.2 * STOCKED_TO_M
    habitat = fishmind.Habitat(bottom_under, about, 2.2 * STOCKED_TO_M, water_level=0.0,
                               refuges=refuges(described, bottom_under, about - span, about + span, rng, coral))
    if coral is not None and len(coral):
        habitat.set_coral(*standing(coral))
    # Each group as the species the place's own record saw, where the record
    # has any with a sheet (fish_species.recorded).
    import fish_species
    import life as life_module

    by = fish_species.recorded(counted, life_module.group_of)
    kinds = fish_species.split({k: v for k, v in groups.items() if v}, by)
    school = fishmind.School(kinds, habitat, seed=seed)
    if light is not None:
        school.hour, school.light = light
    say("life_is", **school.said(), refuges={k: len(v) for k, v in habitat.refuges.items()},
        stockedToM=STOCKED_TO_M, asked=wanted, drawn=how_many,
        perSquareMetre=says.get("perSquareMetre"),
        asRecorded={g: [k for k, _ in v] for g, v in by.items()})
    return school
