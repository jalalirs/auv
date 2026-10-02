"""The coral: colonies that stand in the vehicle's way, and break when it hits them.

Reads    contacts (what the vehicle struck this tick), the wash, the water
Writes   coral: every colony — where, how big, what kind, and what has
         happened to it

Each colony is a column of its own size standing on the seabed, which is what
the vehicle meets (systems/contact.py stops it there, as it stops it at rock).
What happens to a colony that is hit depends on what it is:

  **Branching and finger corals** are a skeleton of thin branches, and they
  snap. A strike's force is its impulse over a contact time of twenty
  milliseconds (assumed: a hard hull on calcium carbonate); the bending moment
  it puts on a branch at the colony's base, over its section modulus π r³/4,
  is the stress; past *Acropora cervicornis*'s measured dynamic strength,
  20.8 ± 5.0 MPa (UCF), it breaks. A branch's radius is a share of the colony's
  size (assumed: a tank frag's are a few millimetres). A broken colony is a
  stump of half its height, and the record keeps where, when, and how hard.
  **Brain and massive corals** do not break under anything a small vehicle
  can do to them (Marshall 2000: *Porites* lost essentially nothing); they are
  struck, and counted.
  **Soft corals, sea fans and sponges** bend out of the way, and are counted as
  brushed rather than struck.

  **Any stony colony can be torn off the rock whole.** The reef rock it is
  cemented to is about a tenth as strong as its skeleton (Madin & Connolly
  2006), so a blow that a massive colony's skeleton shrugs off can still lever
  it off its base: the bending moment at the base, over the section modulus of
  an attachment a quarter of the colony's size across, against 2 MPa
  (assumed: a tenth of the skeleton's dynamic strength). A torn-off colony
  lies on its side; the record says so.
  **What settles on it** (systems/sediment.py) is counted against the dose
  the coral literature gives: harm from about 10 mg cm⁻² a day, severe past
  50 (Erftemeijer et al. 2012). Over a dive that lasts minutes, the dose is
  the rate: what settled, over the fraction of a day it took. Past the first,
  a colony is smothered and the record says so.

What is not here yet: the polyps' day, and the flow tearing a colony off on
its own (Madin's colony shape factor against the drag of a storm).
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

# How each growth form takes a blow.
BREAKS = {"branching", "finger", "table"}
STANDS = {"brain", "massive", "encrusting"}
BENDS = {"plume", "fan", "sponge", "soft"}

# Acropora cervicornis, dynamic fracture strength (UCF honours thesis; the
# quasi-static figure is 8.6 ± 3.0 MPa). Pascals.
BREAKING_STRESS = 20.8e6
# A strike's duration, seconds: hull on skeleton. Assumed.
CONTACT_TIME = 0.02
# A branch's radius as a share of its colony's size. Assumed: a sixteen
# centimetre tank colony has branches about six millimetres thick.
BRANCH_SHARE = {"branching": 0.04, "finger": 0.08, "table": 0.03}
# The reef rock a colony is cemented to: a tenth of the skeleton (Madin &
# Connolly 2006; the figure assumed). Pascals. And how wide the attachment is,
# as a share of the colony's size.
SUBSTRATE_STRESS = 2.0e6
BASE_SHARE = 0.25
# Sediment, mg cm⁻² a day: where harm begins, and where it is severe.
SMOTHERS_FROM = 10.0
SMOTHERS_BADLY = 50.0


class Colonies:
    """Every colony in the place, and its state."""

    def __init__(self) -> None:
        self.at = np.zeros((0, 3))          # base, world, metres
        self.size = np.zeros(0)             # height, metres
        self.kind = np.array([], dtype=object)
        self.prim = []                      # the drawn colony, when the place names it
        self.height = np.zeros(0)           # what stands now: a stump is half
        self.broken = np.zeros(0, dtype=bool)
        self.broken_at = np.full(0, np.nan)
        self.struck = np.zeros(0, dtype=int)
        self.brushed = np.zeros(0, dtype=int)
        self.worst_stress = np.zeros(0)
        self.torn_off = np.zeros(0, dtype=bool)
        self.smothered = np.zeros(0, dtype=int)     # 0 none, 1 harmed, 2 badly
        self.events: list[dict] = []
        self.from_ = "nothing yet"

    @property
    def radius(self) -> np.ndarray:
        """How wide each stands, as a column: half its size, a little less."""
        return 0.42 * self.size

    def __len__(self) -> int:
        return len(self.size)

    def solid(self) -> np.ndarray:
        """Which colonies stop a vehicle: everything that does not bend, and
        has not been torn off and knocked over."""
        return np.array([k not in BENDS for k in self.kind], dtype=bool) & ~self.torn_off

    def said(self) -> dict:
        broken = np.flatnonzero(self.broken)
        return {"colonies": int(len(self)),
                "struck": int((self.struck > 0).sum()), "brushed": int((self.brushed > 0).sum()),
                "broken": [{"kind": str(self.kind[i]), "at": [round(float(c), 3) for c in self.at[i]],
                            "sizeM": round(float(self.size[i]), 3), "t": round(float(self.broken_at[i]), 2),
                            "stressMPa": round(float(self.worst_stress[i]) / 1e6, 1)} for i in broken],
                **({} if not self.torn_off.any() else {"tornOff": [
                    {"kind": str(self.kind[i]), "at": [round(float(c), 3) for c in self.at[i]]}
                    for i in np.flatnonzero(self.torn_off)]}),
                **({} if not self.smothered.any() else {
                    "smothered": int((self.smothered >= 1).sum()),
                    "smotheredBadly": int((self.smothered >= 2).sum())}),
                "from": self.from_}


def colonies_of(described: dict, bottom_under) -> Colonies:
    """The colonies a place's record lists, stood on its seabed."""
    c = Colonies()
    rows = (described.get("reef") or {}).get("colonies_at") or []
    at, size, kind, prim = [], [], [], []
    for row in rows:
        if not row.get("at"):
            continue
        x, y = float(row["at"][0]), float(row["at"][1])
        at.append((x, y, float(bottom_under(x, y))))
        size.append(float(row.get("sizeM", 0.1)))
        kind.append(str(row.get("kind", "massive")))
        prim.append(row.get("prim"))
    n = len(at)
    c.at = np.array(at, dtype=float).reshape(n, 3)
    c.size = np.array(size, dtype=float)
    c.kind = np.array(kind, dtype=object)
    c.prim = prim
    c.height = c.size.copy()
    c.broken = np.zeros(n, dtype=bool)
    c.broken_at = np.full(n, np.nan)
    c.struck = np.zeros(n, dtype=int)
    c.brushed = np.zeros(n, dtype=int)
    c.worst_stress = np.zeros(n)
    c.torn_off = np.zeros(n, dtype=bool)
    c.smothered = np.zeros(n, dtype=int)
    c.from_ = ("the place's record of its colonies; breaking from Acropora's measured strength "
               "with an assumed branch size and contact time")
    return c


def dose_per_day(settled_mg_cm2, seconds: float):
    """What has settled, as the daily rate the thresholds are given in."""
    return settled_mg_cm2 / max(seconds / 86400.0, 1.0 / 24.0)


def stress_of(impulse_ns: float, height_m: float, kind: str, size_m: float) -> float:
    """The bending stress a strike puts on a colony's branches at their base, Pa."""
    force = impulse_ns / CONTACT_TIME
    lever = 0.6 * height_m
    r = BRANCH_SHARE.get(kind, 0.05) * size_m
    return force * lever / (math.pi * r ** 3 / 4.0)


def base_stress_of(impulse_ns: float, height_m: float, size_m: float) -> float:
    """The bending stress a strike puts on the rock a colony is cemented to, Pa."""
    force = impulse_ns / CONTACT_TIME
    r = BASE_SHARE * size_m
    return force * 0.6 * height_m / (math.pi * r ** 3 / 4.0)


class CoralSystem(System):
    name = "coral"
    reads = ("contacts", "clock")
    before = ("sediment",)
    writes = ("coral",)

    def __init__(self, say) -> None:
        self.say = say
        self.seen = 0

    def judge_the_sediment(self, world) -> None:
        _judge(world.coral, world.sediment.on_coral_mg_cm2, world.clock.simulated, self.say)

    def step(self, world) -> None:
        self.judge_the_sediment(world)
        coral, hits = world.coral, world.contacts.coral_hits
        while self.seen < len(hits):
            hit = hits[self.seen]
            self.seen += 1
            i, impulse = int(hit["colony"]), float(hit["impulseNs"])
            kind = str(coral.kind[i])
            if kind in BENDS:
                coral.brushed[i] += 1
                continue
            coral.struck[i] += 1
            # Torn off whole: the colonies that do not snap first. A branching
            # colony's branches give long before its base does.
            if not coral.torn_off[i] and kind not in BENDS and kind not in BREAKS:
                base = base_stress_of(impulse, float(coral.height[i]), float(coral.size[i]))
                if base > SUBSTRATE_STRESS:
                    coral.torn_off[i] = True
                    event = {"growth": kind, "colony": i, "at": [round(float(c), 3) for c in coral.at[i]],
                             "baseStressMPa": round(base / 1e6, 2), "impulseNs": round(impulse, 3)}
                    coral.events.append({"tornOff": True, **event})
                    self.say("coral_torn_off", **event)
                    continue
            if kind not in BREAKS or coral.broken[i]:
                continue
            stress = stress_of(impulse, float(coral.height[i]), kind, float(coral.size[i]))
            coral.worst_stress[i] = max(coral.worst_stress[i], stress)
            if stress > BREAKING_STRESS:
                coral.broken[i] = True
                coral.broken_at[i] = world.clock.simulated
                coral.height[i] = 0.5 * coral.size[i]
                event = {"growth": kind, "colony": i, "at": [round(float(c), 3) for c in coral.at[i]],
                         "stressMPa": round(stress / 1e6, 1), "impulseNs": round(impulse, 3),
                         "speedMs": round(float(hit["speedMs"]), 3)}
                coral.events.append(event)
                self.say("coral_broken", **event)


def _judge(coral, settled, seconds, say):
    """Smothering, from the dose: once a level is passed, said once."""
    if settled is None or len(settled) != len(coral):
        return
    dose = dose_per_day(np.asarray(settled), seconds)
    level = np.where(dose >= SMOTHERS_BADLY, 2, np.where(dose >= SMOTHERS_FROM, 1, 0))
    worse = np.flatnonzero(level > coral.smothered)
    for i in worse:
        coral.smothered[i] = level[i]
        say("coral_smothered", colony=int(i), growth=str(coral.kind[i]),
            mgCm2PerDay=round(float(dose[i]), 1), badly=bool(level[i] >= 2))
