"""Fish with minds: who they are, what they want, when, and how they swim.

Every fish on this platform is one row of the arrays below, stepped together,
in a reef of two thousand or a tank of twenty. Four layers, each from a
literature rather than from taste:

  **A species** (`fish_species`): size, swimming, schooling, territory, home
  range, height off the bottom, when it is active, where it sleeps, what it
  eats, how close it lets a vehicle come.

  **A mind** (after Tu & Terzopoulos, *Artificial Fishes*, 1994): internal
  drives — hunger that rises while it is not feeding, fear that spikes when
  something comes at it and fades, and the urge to be active that follows the
  light — weighed against its species' habits and a personality of its own
  (bold or shy, lively or idle). From them an intention: rest, forage,
  school, patrol, wander or flee. It holds an intention for a while and then
  thinks again, so no two fish do the same thing at the same time and none
  of them changes its mind every frame.

  **A day** (the diel cycle the tracking studies show): diurnal fish feed by
  day and go into their refuge at dusk — a chromis into the coral's
  branches, a parrotfish into a crevice, a wrasse into the sand, a clownfish
  into its host — and nocturnal ones come out as the light goes. In a tank
  the day is the lights'.

  **A stroke** (burst-and-coast, Calovi et al. 2018, Lei et al. 2020): a
  fish swims in kicks. Each kick turns it and accelerates it; then it glides
  straight while it slows. Where it turns at a kick is the sum of where its
  intention takes it, attraction to and alignment with its one to three most
  influential neighbours of its own kind, the glass or the ground ahead, and
  a fluctuation of its own. That is why a real school looks alive and a
  flock of particles does not.

What a fish sees of the vehicle is how fast it grows in its view. Wild reef
fish decide to flee on the looming rate — how fast a threat's angular size
grows — held back by how big it already looks and by how many of their own
kind are about them (Hein et al. 2018, twelve species at Moorea, 82–98% of
escapes predicted). Here that is the shape of the rule, with its threshold set
so that a vehicle closing at fifteen centimetres a second is half-frightening
at the species' flight distance (Gotanda 2009, Feary 2011 for the
distances); the numbers of the rule are chosen, not fitted. A frightened fish
first turns away for a quarter of a second, then makes for its refuge, and
comes back when the fear has faded. A noisier vehicle is seen from further.

And they are in the water: carried by whatever the water is doing where they
are — the current, and the vehicle's own wash — and they turn to face into
it as fish do. They steer round rock rather than through it, and a fish the
vehicle runs into is knocked aside and counted.
"""

from __future__ import annotations

import math

import numpy as np

try:
    from coral import fish_species
except ImportError:          # the runtime puts coral/ itself on the path
    import fish_species

REST, FORAGE, SCHOOL, PATROL, WANDER, FLEE = range(6)
MODES = ("rest", "forage", "school", "patrol", "wander", "flee")
DIURNAL, NOCTURNAL, CREPUSCULAR = range(3)
ACTIVITY = {"diurnal": DIURNAL, "nocturnal": NOCTURNAL, "crepuscular": CREPUSCULAR}
REFUGES = ("branch", "crevice", "burrow", "host", "open")

# How hard each intention swims, as a share of the species' burst, and how
# much longer than usual it waits between kicks.
VIGOUR = np.array([0.35, 0.75, 1.0, 0.85, 0.7, 2.2])
PAUSE = np.array([3.5, 1.3, 1.0, 1.1, 1.2, 0.35])


def daylight(hour: float, rises: float = 6.0, sets: float = 18.5, twilight: float = 0.75) -> float:
    """How much light there is, 0..1, from the hour: a smooth dawn and dusk."""
    up = 0.5 + 0.5 * math.tanh((hour - rises) / (twilight / 2.0))
    down = 0.5 - 0.5 * math.tanh((hour - sets) / (twilight / 2.0))
    return float(max(0.0, min(1.0, up * down)))


class Habitat:
    """What the fish know about where they live: the bottom, the glass if
    there is glass, the surface, and the places they can hide."""

    def __init__(self, floor_at, about, across: float, water_level: float = 0.0,
                 box=None, refuges: dict | None = None, scale: float = 1.0) -> None:
        self.about = np.asarray(about, dtype=float)
        self.across = float(across)
        self.water_level = float(water_level)
        self.box = None if box is None else np.asarray(box, dtype=float)
        self.scale = float(scale)
        self.refuges = {k: np.asarray(v, dtype=float).reshape(-1, 3) for k, v in (refuges or {}).items()}
        n = 160
        edge = 0.5 * self.across
        self._line_x = np.linspace(self.about[0] - edge, self.about[0] + edge, n)
        self._line_y = np.linspace(self.about[1] - edge, self.about[1] + edge, n)
        grid = np.empty((n, n))
        for j, y in enumerate(self._line_y):
            for i, x in enumerate(self._line_x):
                got = floor_at(float(x), float(y))
                grid[j, i] = -30.0 if got is None else float(got)
        self._floor = grid

    def floor(self, xy) -> np.ndarray:
        xy = np.atleast_2d(xy)
        n = len(self._line_x)
        edge = 0.5 * self.across
        u = np.clip((xy[:, 0] - self.about[0] + edge) / (2 * edge) * (n - 1), 0, n - 1.001)
        v = np.clip((xy[:, 1] - self.about[1] + edge) / (2 * edge) * (n - 1), 0, n - 1.001)
        i, j = u.astype(int), v.astype(int)
        fu, fv = u - i, v - j
        g = self._floor
        return ((g[j, i] * (1 - fu) + g[j, i + 1] * fu) * (1 - fv)
                + (g[j + 1, i] * (1 - fu) + g[j + 1, i + 1] * fu) * fv)

    def inside(self, xy, margin: float = 0.0) -> np.ndarray:
        """Clamp to where water is: the glass, or the stocked square."""
        half = self.box if self.box is not None else np.array([0.49 * self.across] * 2)
        margin = np.asarray(margin, dtype=float)
        if margin.ndim:
            margin = margin[:, None]
        return np.clip(xy, self.about - half + margin, self.about + half - margin)


class School:
    """Every fish in a place, with a mind each, stepped together."""

    def __init__(self, stock: dict, habitat: Habitat, clock=None, seed: int = 0, tank: bool = False) -> None:
        self.rng = np.random.default_rng(seed)
        self.habitat = habitat
        # simulated seconds -> (hour, light), for a school stepped on its own;
        # a dive hands the light in with each step instead.
        self.clock = clock
        self.hour, self.light = 12.0, 1.0
        self._size = 0.2
        self.t = 0.0
        kinds = []
        for name, many in sorted(stock.items()):
            kinds += [fish_species.species_of(name, tank=tank)] * int(many)
        self.kinds = np.array(kinds)
        self.of_them = n = len(kinds)
        self._kinds_present = sorted(set(kinds))
        self._of_kind = {k: np.flatnonzero(self.kinds == k) for k in self._kinds_present}
        sheets = [fish_species.SPECIES[k] for k in kinds]
        d = habitat.scale
        take = lambda key: np.array([s[key] for s in sheets], dtype=float)  # noqa: E731
        self.length = np.array([self.rng.uniform(*s["length"]) for s in sheets], dtype=float)
        self.kick_s, self.coast_s = take("kick_s"), take("coast_s")
        self.burst = take("burst_bl") * self.length
        self.turn = np.radians(take("turn_deg"))
        # Distances a reef's fish use, shrunk to the water there is. Not all
        # by the same: a chromis two metres up a reef is not nine centimetres
        # up a tank, it is in the middle of the water, and one that bolts at
        # a vehicle a metre off still bolts at one a third of a metre off.
        self.flight = take("flight_m") * max(d, 0.3)
        self.home_range = take("home_m") * d
        self.territory = np.array([(s["territory_m"] or 0.0) * max(d, 0.4) for s in sheets])
        self.altitude = np.array([s["altitude_m"][0] for s in sheets]) * max(d, 0.5)
        self.altitude_sd = np.array([s["altitude_m"][1] for s in sheets]) * max(d, 0.5)
        self.activity = np.array([ACTIVITY[s["activity"]] for s in sheets], dtype=int)
        self.refuge_of = np.array([REFUGES.index(s["refuge"]) for s in sheets], dtype=int)
        self.diet = np.array([s["diet"] for s in sheets])
        self.schools = np.array([s["school"] is not None for s in sheets])
        self.attract = np.array([(s["school"] or {}).get("attract", 0.0) for s in sheets])
        self.align = np.array([(s["school"] or {}).get("align", 0.0) for s in sheets])
        self.neighbours = np.array([(s["school"] or {}).get("neighbours", 0) for s in sheets], dtype=int)
        self.social_range = np.array([(s["school"] or {}).get("range_bl", 0.0) for s in sheets]) * self.length
        # A personality each: bold or shy, lively or idle.
        self.bold = np.clip(self.rng.normal(1.0, 0.2, n), 0.5, 1.6)
        self.lively = np.clip(self.rng.normal(1.0, 0.15, n), 0.6, 1.4)
        self.hunger = self.rng.uniform(0.2, 0.7, n)
        self.fear = np.zeros(n)
        self.mode = np.full(n, WANDER, dtype=int)
        self.mode_until = self.rng.uniform(0.0, 3.0, n)
        self.home = self._homes()
        self.centre = self.home.copy()            # a territory's middle is its home
        self.goal = self.home.copy()
        self.at = self.home + np.column_stack([self.rng.normal(0, 0.1 * d + 0.02, (n, 2)), np.zeros(n)])
        self.at[:, :2] = habitat.inside(self.at[:, :2], 0.02)
        self.at[:, 2] = habitat.floor(self.at[:, :2]) + np.maximum(self.altitude, 0.3 * self.length)
        self.heading = self.rng.uniform(-np.pi, np.pi, n)
        self.speed = self.burst * 0.3
        self.vz = np.zeros(n)
        self.kick_in = self.rng.uniform(0, 1, n) * self.kick_s
        self.kicking = np.zeros(n)
        self.turning = np.zeros(n)
        self.beat = self.rng.uniform(0, 2 * np.pi, n)
        self.scattered = 0.0
        self.budget = np.zeros((n, len(MODES)))
        # The vehicle as each fish last saw it: how far, to work out how fast
        # it is closing; and when each last bolted.
        self._gap = np.full(n, np.inf)
        self._vehicle = None
        self._was = None
        self._touching = np.zeros(n, dtype=bool)
        self.fled_at = np.full(n, -np.inf)
        self._flow = np.zeros((n, 3))
        # Fish the vehicle ran into, and how many times; and strikes by
        # predators on prey.
        self.bumped = 0
        self.strikes = 0
        self._chasing: dict = {}
        self._chase_gap: dict = {}
        # What the vehicle's camera has seen: each fish once, and how many
        # were in view each time it looked (systems/fish.py counts).
        self.counted: set[int] = set()
        self.in_view: list[int] = []
        self._sync()

    # ── where they live ──────────────────────────────────────────────────────

    def _homes(self) -> np.ndarray:
        """Where each fish lives: a refuge of its species' kind.

        Fish of a kind come in groups — a school, a pair, a fish alone — and
        each group has its own patch of the place, as on a real reef, where a
        kind is a dozen separate schools and not one cloud. In the patch each
        fish takes the nearest refuge it would use: a chromis a branching
        coral, a parrotfish a crevice in the rock, a goby a burrow in the sand.
        """
        hab = self.habitat
        n = self.of_them
        homes = np.zeros((n, 3))
        self.school = np.zeros(n, dtype=int)
        half = hab.box if hab.box is not None else np.array([0.45 * hab.across] * 2)
        everywhere = np.vstack(list(hab.refuges.values())) if hab.refuges else None
        groups = 0
        for k, idx in self._of_kind.items():
            first = int(idx[0])
            size = (4, 24) if self.schools[first] and self.neighbours[first] >= 2 else \
                   (2, 2) if self.schools[first] else (1, 1)
            put = 0
            while put < len(idx):
                many = min(int(self.rng.integers(size[0], size[1] + 1)), len(idx) - put)
                patch = hab.about + self.rng.uniform(-0.85, 0.85, 2) * half
                want = REFUGES[self.refuge_of[first]]
                places = hab.refuges.get(want)
                if want == "host" and places is None:
                    places = hab.refuges.get("branch")
                if want == "open" or places is None or not len(places):
                    places = everywhere
                for i in idx[put:put + many]:
                    if places is not None and len(places):
                        gap = np.hypot(places[:, 0] - patch[0], places[:, 1] - patch[1])
                        near = np.argsort(gap)[:max(1, min(3, len(places)))]
                        homes[i] = places[self.rng.choice(near)]
                        if want == "open":
                            homes[i, :2] += self.rng.normal(0, 0.05 * max(hab.scale, 0.3), 2)
                    else:
                        xy = hab.inside(patch + self.rng.normal(0, 0.03 + 0.05 * hab.scale, 2), 0.05)
                        homes[i] = (xy[0], xy[1], float(hab.floor(xy)[0]))
                    self.school[i] = groups
                put += many
                groups += 1
        homes[:, :2] = hab.inside(homes[:, :2], 0.03)
        return homes

    # ── the day ──────────────────────────────────────────────────────────────

    def awake(self, light: float) -> np.ndarray:
        """How active each fish is at this light, 0..1, by its species' habit."""
        def ramp(v, a, b):
            return np.clip((v - a) / (b - a), 0.0, 1.0)
        day = ramp(light, 0.12, 0.4)
        night = 1.0 - ramp(light, 0.05, 0.3)
        dusk = np.clip(1.0 - abs(light - 0.3) / 0.3, 0.0, 1.0)
        return np.select([self.activity == DIURNAL, self.activity == NOCTURNAL],
                         [day, night], np.maximum(dusk, 0.5 * day))

    # ── the mind ─────────────────────────────────────────────────────────────

    # The looming rule's shape. CLOSING is the approach speed, metres a
    # second, at which a vehicle at a fish's flight distance frightens it by
    # half; STEEP is how sharply fear rises with the log of the looming rate
    # about that; CROWD is how much a fish surrounded by its own kind is held
    # back. Chosen, after Hein et al. 2018, not fitted.
    CLOSING = 0.15
    STEEP = 3.0
    CROWD = 0.3

    def threat(self, dt: float, vehicle, size: float, thrust: float) -> np.ndarray:
        """How frightening the vehicle is to each fish, 0..1, from how fast it
        is growing in the fish's view."""
        n = self.of_them
        if vehicle is None:
            self._gap[:] = np.inf
            self._was = None
            return np.zeros(n)
        vehicle = np.asarray(vehicle, dtype=float)
        off = self.at - vehicle[None, :]
        far = np.maximum(np.linalg.norm(off, axis=1), 1e-6)
        gap = np.maximum(far - size, 0.01)
        # How fast the *vehicle* is closing on each fish. Not the gap's own
        # rate: a fish swimming up to a vehicle that is sitting still makes
        # it grow in its eye too, and does not bolt from what it is
        # approaching itself.
        moving = np.zeros(3) if self._was is None else (vehicle - self._was) / max(dt, 1e-6)
        self._was = vehicle.copy()
        closing = (off / far[:, None]) @ moving      # its velocity towards each fish
        self._gap = gap
        # Angular size S = 2 atan(R/d), and its rate S' = 2R d'/(d² + R²).
        looming = 2.0 * size * np.maximum(closing, 0.0) / (gap ** 2 + size ** 2)
        # Seen from further when it is loud: a vehicle on full thrust clears a
        # reef that one drifting past does not.
        reach = self.flight / self.bold * (1.0 + 0.6 * min(1.0, max(0.0, thrust)))
        critical = 2.0 * size * self.CLOSING / (reach ** 2 + size ** 2)
        with np.errstate(divide="ignore"):
            frightened = 1.0 / (1.0 + np.exp(-self.STEEP * (np.log(np.maximum(looming, 1e-9))
                                                             - np.log(critical))))
        # Held back by company: the share of its own kind within four body
        # lengths, up to four of them.
        company = np.zeros(n)
        for k, mates in self._of_kind.items():
            if len(mates) < 2:
                continue
            d = np.linalg.norm(self.at[mates][:, None, :] - self.at[mates][None, :, :], axis=2)
            near = (d < 4.0 * self.length[mates][:, None]).sum(axis=1) - 1
            company[mates] = np.minimum(1.0, near / 4.0)
        frightened = frightened * (1.0 - self.CROWD * company)
        # And uneasy, looming or not, with something that big right beside it.
        beside = np.clip(1.0 - gap / np.maximum(0.4 * reach, 1e-6), 0.0, 1.0)
        return np.maximum(frightened, beside)

    # A predator hunts what is under half its own length, within this many of
    # its own lengths, and strikes when it closes to half a length. Chosen.
    PREY_UNDER = 0.5
    HUNTS_WITHIN_BL = 25.0

    def hunt(self, dt: float) -> None:
        """Fish that eat fish, and the fish they eat.

        A predator foraging picks out the nearest fish under half its length
        and makes for it, refreshed every step, so the chase is a chase; a fish
        a predator is closing on is frightened by the same looming rule as a
        vehicle (its size, how fast it closes). A predator that closes to half
        a length has struck: counted, and the prey bolts. Nothing is eaten — a
        reef's count stays the count a survey is scored against — but what a
        predator does to a school is what a diver sees on a reef: it tightens,
        and it runs."""
        hunters = np.flatnonzero((self.diet == "fish") & (self.mode == FORAGE))
        if not len(hunters):
            self._chasing = {}
            return
        chasing = {}
        for h in hunters:
            reach = self.HUNTS_WITHIN_BL * self.length[h]
            prey = np.flatnonzero(self.length < self.PREY_UNDER * self.length[h])
            if not len(prey):
                continue
            far = np.linalg.norm(self.at[prey] - self.at[h][None, :], axis=1)
            near = int(np.argmin(far))
            if far[near] > reach:
                continue
            target = int(prey[near])
            chasing[int(h)] = target
            # Make for it: the goal is where it is now.
            self.goal[h] = self.at[target]
            self.mode_until[h] = max(self.mode_until[h], self.t + 1.0)
            # It strikes, or it frightens.
            if far[near] < 0.5 * self.length[h]:
                self.strikes += 1
                self.fear[target] = 1.0
            else:
                closing = 0.0
                was = getattr(self, "_chasing", {}).get(int(h))
                if was == target and getattr(self, "_chase_gap", {}).get(int(h)) is not None:
                    closing = (self._chase_gap[int(h)] - far[near]) / max(dt, 1e-6)
                size = 0.5 * self.length[h]
                looming = 2.0 * size * max(closing, 0.0) / (far[near] ** 2 + size ** 2)
                critical = 2.0 * size * self.CLOSING / (self.flight[target] ** 2 + size ** 2)
                if looming > 0:
                    afraid = 1.0 / (1.0 + math.exp(-self.STEEP * (math.log(looming) - math.log(critical))))
                    self.fear[target] = max(self.fear[target], afraid)
        self._chase_gap = {h: float(np.linalg.norm(self.at[t] - self.at[h])) for h, t in chasing.items()}
        self._chasing = chasing

    def think(self, dt: float, light: float, vehicle, thrust: float, size: float = 0.2) -> None:
        n = self.of_them
        awake = self.awake(light)
        # Hunger rises while it is not feeding and falls while it is.
        feeding = self.mode == FORAGE
        self.hunger = np.clip(self.hunger + dt * np.where(feeding, -1 / 90.0, 1 / 600.0 * awake), 0.0, 1.0)
        # Fear: what is coming at it, fading.
        self.fear *= math.exp(-dt / 4.0)
        self.fear = np.maximum(self.fear, self.threat(dt, vehicle, size, thrust))
        self.hunt(dt)
        self.scattered = float((self.fear > 0.5).mean()) if n else 0.0
        bolting = (self.fear > 0.5) & (self.mode != FLEE)
        if bolting.any():
            # A startle is a kick now, not at the next one due.
            self.fled_at[bolting] = self.t
            self.kick_in[bolting] = 0.0

        due = (self.mode_until <= self.t) | bolting
        if not due.any():
            return
        idx = np.flatnonzero(due)
        r = self.rng.random(len(idx))
        mode = np.full(len(idx), WANDER)
        afraid = self.fear[idx] > 0.5
        sleepy = awake[idx] < 0.45
        territorial = self.territory[idx] > 0
        hungry = self.hunger[idx] > 0.55
        schooling = self.schools[idx]
        mode = np.where(schooling & (r < 0.75), SCHOOL, mode)
        mode = np.where(hungry & (r < 0.85), FORAGE, mode)
        mode = np.where(territorial, np.where(r < 0.65, PATROL, FORAGE), mode)
        mode = np.where(sleepy, REST, mode)
        mode = np.where(afraid, FLEE, mode)
        self.mode[idx] = mode
        # How long it keeps this intention: a random mind, not a clock.
        keep = self.rng.exponential(12.0, len(idx)) + 3.0
        keep = np.where(mode == FLEE, self.rng.uniform(2.0, 5.0, len(idx)), keep)
        keep = np.where(mode == REST, 20.0 + keep, keep)
        self.mode_until[idx] = self.t + keep
        self.goal[idx] = self._goals(idx, mode, vehicle)

    def _goals(self, idx, mode, vehicle) -> np.ndarray:
        hab = self.habitat
        goals = np.zeros((len(idx), 3))
        for n, (i, m) in enumerate(zip(idx, mode)):
            home = self.home[i]
            if m == REST:
                xy = home[:2] + self.rng.normal(0, 0.02, 2)
                z = home[2] + (0.03 if REFUGES[self.refuge_of[i]] != "open" else self.altitude[i])
            elif m == FLEE:
                if vehicle is not None and REFUGES[self.refuge_of[i]] == "open":
                    away = self.at[i, :2] - np.asarray(vehicle)[:2]
                    xy = self.at[i, :2] + away / max(np.linalg.norm(away), 1e-6) * self.flight[i]
                else:
                    xy = home[:2]
                z = home[2] + 0.03
            elif m == PATROL:
                a = self.rng.uniform(-np.pi, np.pi)
                rad = self.territory[i] * self.rng.uniform(0.3, 0.9)
                xy = self.centre[i, :2] + rad * np.array([math.cos(a), math.sin(a)])
                z = None
            elif m == FORAGE and self.diet[i] in ("algae", "inverts"):
                # Picking at the substrate: a point on the rock or coral near home.
                pool = [v for k, v in hab.refuges.items() if k in ("crevice", "branch") and len(v)]
                pool = np.vstack(pool) if pool else None
                if pool is not None:
                    gap = np.hypot(pool[:, 0] - home[0], pool[:, 1] - home[1])
                    near = np.flatnonzero(gap < max(self.home_range[i], 0.2))
                    pick = pool[self.rng.choice(near)] if len(near) else pool[np.argmin(gap)]
                    xy = pick[:2] + self.rng.normal(0, 0.03, 2)
                else:
                    xy = home[:2] + self.rng.normal(0, self.home_range[i] * 0.3, 2)
                z = float(hab.floor(xy)[0]) + max(0.03, 0.6 * self.length[i])
            else:
                # Plankton picking, wandering, and where a school is heading:
                # somewhere in its home range, at its height.
                spread = max(self.home_range[i] * 0.4, 0.1)
                xy = home[:2] + self.rng.normal(0, spread, 2)
                z = None
            xy = hab.inside(np.asarray(xy, dtype=float), 0.04 + 0.5 * self.length[i])
            # Not inside a rock: somewhere else in the same water, if the
            # place it picked is a boulder standing higher than it means to be.
            if m not in (REST, FLEE) and z is None:
                for _ in range(6):
                    if float(hab.floor(xy)[0]) < float(self.at[i, 2]) - 0.3 * self.length[i]:
                        break
                    xy = hab.inside(self.at[i, :2] + self.rng.normal(0, max(self.home_range[i] * 0.3, 0.1), 2),
                                    0.04 + 0.5 * self.length[i])
            if z is None:
                z = float(hab.floor(xy)[0]) + max(0.3 * self.length[i],
                                                  self.rng.normal(self.altitude[i], self.altitude_sd[i]))
            goals[n] = (xy[0], xy[1], min(z, hab.water_level - 0.04))
        return goals

    # ── the stroke ───────────────────────────────────────────────────────────

    def kick(self, idx) -> None:
        """Where each fish due a kick turns, and how hard it goes."""
        hab = self.habitat
        at, here = self.at[idx], self.at[idx, :2]
        to_goal = self.goal[idx, :2] - here
        gap = np.linalg.norm(to_goal, axis=1)
        want = to_goal / np.maximum(gap, 1e-6)[:, None] * np.minimum(1.0, gap / 0.05)[:, None]
        # A startled fish turns away from the threat first, for the length of
        # a C-start and the glide after it, and only then makes for shelter.
        if self._vehicle is not None:
            startled = (self.mode[idx] == FLEE) & (self.t - self.fled_at[idx] < 0.3)
            if startled.any():
                away = here[startled] - self._vehicle[:2]
                want[startled] = away / np.maximum(np.linalg.norm(away, axis=1, keepdims=True), 1e-6)
                gap[startled] = np.maximum(gap[startled], 1.0)
        # And clear of it while frightened: shelter is no use through the
        # vehicle, and a fish making for its coral goes round what scared it.
        if self._vehicle is not None:
            away = here - self._vehicle[:2]
            far = np.maximum(np.linalg.norm(away, axis=1), 1e-6)
            near = np.clip(1.0 - far / np.maximum(4.0 * self._size, 0.05), 0.0, 1.0)
            want += (3.0 * near * np.minimum(1.0, self.fear[idx] * 2.0))[:, None] * away / far[:, None]
        # Into the water's flow, as fish hold station: the stronger it runs
        # against what the fish can do, the more it faces into it.
        flow = self._flow[idx, :2]
        want -= flow / np.maximum(0.5 * self.burst[idx], 0.02)[:, None]
        # Social: attraction to and alignment with the most influential few
        # neighbours of its own kind — the nearest, inside its range.
        for k in self._kinds_present:
            mates = self._of_kind[k]
            mine = idx[self.kinds[idx] == k]
            if len(mates) < 2 or len(mine) == 0 or self.neighbours[mine[0]] == 0:
                continue
            rows = np.searchsorted(idx, mine)
            off = self.at[mates][None, :, :2] - self.at[mine][:, None, :2]
            far = np.linalg.norm(off, axis=2)
            far[mine[:, None] == mates[None, :]] = np.inf
            far[far > self.social_range[mine][:, None]] = np.inf
            take = min(int(self.neighbours[mine[0]]), len(mates) - 1)
            near = np.argsort(far, axis=1)[:, :take]
            for c in range(take):
                j = near[:, c]
                d = far[np.arange(len(mine)), j]
                ok = np.isfinite(d)
                if not ok.any():
                    continue
                unit = off[np.arange(len(mine)), j] / np.maximum(d, 1e-6)[:, None]
                body = self.length[mine]
                # Attraction past two body lengths, repulsion inside one.
                pull = np.tanh((d - 2.0 * body) / np.maximum(body, 1e-6))
                theirs = np.column_stack([np.cos(self.heading[mates][j]), np.sin(self.heading[mates][j])])
                social = (self.attract[mine] * pull)[:, None] * unit + self.align[mine][:, None] * theirs
                in_school = (self.mode[mine] == SCHOOL) | (self.mode[mine] == FORAGE)
                social[~ok | ~in_school] = 0.0
                want[rows] += social
        # The glass, felt from a few body lengths out.
        if hab.box is not None:
            low, high = hab.about - hab.box, hab.about + hab.box
            reach = np.maximum(4.0 * self.length[idx], 0.06)
            for axis in (0, 1):
                want[:, axis] += 1.5 * np.exp(-(here[:, axis] - low[axis]) / reach)
                want[:, axis] -= 1.5 * np.exp(-(high[axis] - here[:, axis]) / reach)
        # And a fluctuation of its own: shy fish dither more.
        noise = self.rng.normal(0, 0.25 / self.bold[idx])
        aim = self.round_the_rock(idx, np.arctan2(want[:, 1], want[:, 0]) + noise)
        turn = (aim - self.heading[idx] + np.pi) % (2 * np.pi) - np.pi
        turn = np.clip(turn, -self.turn[idx], self.turn[idx])
        duration = np.clip(self.rng.normal(0.14, 0.03, len(idx)), 0.08, 0.25)
        self.turning[idx] = turn / duration
        self.kicking[idx] = duration
        awake = np.maximum(self.awake(self.light)[idx], 0.25)
        go = self.burst[idx] * VIGOUR[self.mode[idx]] * self.lively[idx] * awake
        # Close to where it wants to be, a fish holds rather than charges.
        go = go * np.clip(gap / np.maximum(4.0 * self.length[idx], 0.04), 0.25, 1.0)
        self.speed[idx] = np.maximum(self.speed[idx], go)
        self.kick_in[idx] = self.rng.gamma(4.0, self.kick_s[idx] * PAUSE[self.mode[idx]] / 4.0)

    # Which way round, in radians either side of where it means to go, tried
    # nearest first.
    DETOURS = np.array([0.0, 0.5, -0.5, 1.0, -1.0, 1.6, -1.6, 2.4, -2.4])

    def round_the_rock(self, idx, aim) -> np.ndarray:
        """The way it means to go, or the nearest way round rock standing in
        it. A fish goes round a boulder rather than up and over it, and never
        through it."""
        hab = self.habitat
        look = np.maximum(3.0 * self.length[idx], 0.05)
        clear = self.at[idx, 2] - 0.3 * self.length[idx]
        chosen = aim.copy()
        open_ = np.zeros(len(idx), dtype=bool)
        for turn in self.DETOURS:
            way = aim + turn
            probe = self.at[idx, :2] + look[:, None] * np.column_stack([np.cos(way), np.sin(way)])
            free = (hab.floor(probe) < clear) & ~open_
            chosen[free] = way[free]
            open_ |= free
            if open_.all():
                break
        # Boxed in on every side: rise over it.
        self.goal[idx[~open_], 2] = np.maximum(self.goal[idx[~open_], 2],
                                               self.at[idx[~open_], 2] + 2.0 * self.length[idx[~open_]])
        return chosen

    def step(self, dt: float, vehicle=None, thrust: float = 0.0, light=None, flow=None,
             vehicle_size: float = 0.2) -> None:
        """One step: think, kick or glide, be carried, and keep out of the
        rock, the glass and the vehicle.

        `light` is (hour, 0..1) from the dive's day; `flow` is the water's
        velocity at each fish (n, 3), the current and the wash together."""
        if not self.of_them or dt <= 0:
            return
        self.t += dt
        if light is not None:
            self.hour, self.light = float(light[0]), float(light[1])
        elif self.clock is not None:
            self.hour, self.light = self.clock(self.t)
        self._flow = np.zeros((self.of_them, 3)) if flow is None else np.asarray(flow, dtype=float)
        self._vehicle = None if vehicle is None else np.asarray(vehicle, dtype=float)
        self._size = float(vehicle_size)
        self.think(dt, self.light, vehicle, thrust, vehicle_size)
        self.kick_in -= dt
        due = np.flatnonzero(self.kick_in <= 0.0)
        if len(due):
            self.kick(due)
        kicking = self.kicking > 0.0
        self.heading = np.where(kicking, self.heading + self.turning * dt, self.heading)
        self.kicking = np.maximum(0.0, self.kicking - dt)
        # The glide: speed decays between kicks.
        self.speed = np.where(kicking, self.speed, self.speed * np.exp(-dt / self.coast_s))
        # Height: towards the intention's, at a pitch a fish would use.
        dz = self.goal[:, 2] - self.at[:, 2]
        self.vz = np.clip(dz * 1.2, -0.4 * self.speed - 0.01, 0.4 * self.speed + 0.01)
        way = np.column_stack([np.cos(self.heading), np.sin(self.heading)])
        # Gliding into rock: turned along it to whichever side is open, as at
        # the glass, rather than lifted over it.
        ahead = self.at[:, :2] + way * np.maximum(self.speed * dt, 0.5 * self.length)[:, None]
        rock = self.habitat.floor(ahead) > self.at[:, 2] - 0.2 * self.length
        if rock.any():
            idx = np.flatnonzero(rock)
            left = self.heading[idx] + np.pi / 2
            right = self.heading[idx] - np.pi / 2
            reach = np.maximum(self.length[idx], 0.03)[:, None]
            lf = self.habitat.floor(self.at[idx, :2] + reach * np.column_stack([np.cos(left), np.sin(left)]))
            rf = self.habitat.floor(self.at[idx, :2] + reach * np.column_stack([np.cos(right), np.sin(right)]))
            self.heading[idx] = np.where(lf <= rf, self.heading[idx] + 0.6, self.heading[idx] - 0.6)
            self.speed[idx] *= 0.5
            way = np.column_stack([np.cos(self.heading), np.sin(self.heading)])
        self.at[:, :2] += way * self.speed[:, None] * dt
        self.at[:, 2] += self.vz * dt
        # Carried by the water: a fish swims through it, not over the ground.
        self.at += self._flow * dt
        if self._vehicle is not None:
            self.keep_out_of_the_vehicle(vehicle_size)
        hab = self.habitat
        held = hab.inside(self.at[:, :2], 0.5 * self.length)
        hit = np.any(np.abs(held - self.at[:, :2]) > 1e-9, axis=1)
        if hit.any():
            # Met the glass: turned along it, as a fish does, not stopped dead.
            normal = held[hit] - self.at[hit, :2]
            normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9)
            along = way[hit] - normal * np.sum(way[hit] * normal, axis=1, keepdims=True)
            self.heading[hit] = np.arctan2(along[:, 1] + 1e-9, along[:, 0])
            self.at[hit, :2] = held[hit]
        floor = hab.floor(self.at[:, :2])
        self.at[:, 2] = np.clip(self.at[:, 2], floor + 0.25 * self.length, hab.water_level - 0.03)
        # The tail: quick strokes in a kick, a slow scull in the glide.
        hz = np.where(kicking, 5.0, 0.7 + 0.3 * self.speed / np.maximum(self.length, 1e-3))
        self.beat += 2 * np.pi * np.minimum(hz, 6.0) * dt
        self.budget[np.arange(self.of_them), self.mode] += dt
        self._sync()

    def keep_out_of_the_vehicle(self, size: float) -> None:
        """A fish the vehicle runs into is knocked aside, frightened, and
        counted. The vehicle does not feel it: a fish is grams against
        kilograms, and the impulse is under the noise of its own control."""
        off = self.at - self._vehicle[None, :]
        far = np.linalg.norm(off, axis=1)
        reach = size + 0.5 * self.length
        inside = far < reach
        # Once a contact, not once a step: a fish pinned against the hull for
        # a second was struck once.
        self.bumped += int((inside & ~self._touching).sum())
        self._touching = inside
        if not inside.any():
            return
        out = off[inside] / np.maximum(far[inside], 1e-6)[:, None]
        self.at[inside] = self._vehicle[None, :] + out * reach[inside][:, None]
        self.heading[inside] = np.arctan2(out[:, 1], out[:, 0])
        self.speed[inside] = np.maximum(self.speed[inside], self.burst[inside])
        self.fear[inside] = 1.0

    def _sync(self) -> None:
        """The shape the drawing and the record read."""
        n = self.of_them
        way = np.column_stack([np.cos(self.heading), np.sin(self.heading), np.zeros(n)]) if n else np.zeros((0, 3))
        self.going = way * self.speed[:, None] if n else np.zeros((0, 3))
        if n:
            self.going[:, 2] = self.vz
        pitch = np.clip(self.vz / np.maximum(self.speed, 0.02), -0.5, 0.5) if n else np.zeros(0)
        self.facing_as = np.column_stack([way[:, 0], way[:, 1], pitch]) if n else np.zeros((0, 3))

    # ── what the record says ─────────────────────────────────────────────────

    def seen_from(self, at, looking, half_angle_deg: float = 32.0, reach: float = 12.0) -> dict:
        if not self.of_them:
            return {}
        off = self.at - np.asarray(at, dtype=float)[None, :]
        far = np.linalg.norm(off, axis=1)
        way = np.asarray(looking, dtype=float)
        way = way / max(float(np.linalg.norm(way)), 1e-9)
        facing = (off @ way) / np.maximum(far, 1e-9)
        inside = (far < reach) & (facing > np.cos(np.radians(half_angle_deg)))
        return {str(k): int((self.kinds[inside] == k).sum()) for k in np.unique(self.kinds[inside])}

    def said(self) -> dict:
        counted = {str(k): int(len(v)) for k, v in self._of_kind.items()}
        spent = {}
        for k, v in self._of_kind.items():
            total = self.budget[v].sum()
            if total > 0:
                spent[str(k)] = {m: round(float(self.budget[v][:, i].sum() / total), 3)
                                 for i, m in enumerate(MODES) if self.budget[v][:, i].sum() > 0}
        return {"fish": int(self.of_them), "bySpecies": counted, "byGroup": counted,
                "schools": int(len(np.unique(self.school))) if self.of_them else 0, "scattered": round(self.scattered, 3),
                "hour": round(float(self.hour), 2), "light": round(float(self.light), 2), "spent": spent,
                "bumped": int(self.bumped),
                **({} if not self.strikes else {"predatorStrikes": int(self.strikes)}),
                **({} if not self.in_view else {
                    "countedByTheCamera": len(self.counted),
                    "inViewMean": round(float(np.mean(self.in_view)), 2),
                    "countedBySpecies": {str(k): int(sum(1 for i in self.counted if self.kinds[i] == k))
                                         for k in self._kinds_present}})}
