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

What is not here yet, and is in r6: being torn off the rock whole (Madin and
Connolly's colony shape factor), sediment settling on a colony and smothering
it, and the polyps' day.
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
        self.events: list[dict] = []
        self.from_ = "nothing yet"

    @property
    def radius(self) -> np.ndarray:
        """How wide each stands, as a column: half its size, a little less."""
        return 0.42 * self.size

    def __len__(self) -> int:
        return len(self.size)

    def solid(self) -> np.ndarray:
        """Which colonies stop a vehicle: everything that does not bend."""
        return np.array([k not in BENDS for k in self.kind], dtype=bool)

    def said(self) -> dict:
        broken = np.flatnonzero(self.broken)
        return {"colonies": int(len(self)),
                "struck": int((self.struck > 0).sum()), "brushed": int((self.brushed > 0).sum()),
                "broken": [{"kind": str(self.kind[i]), "at": [round(float(c), 3) for c in self.at[i]],
                            "sizeM": round(float(self.size[i]), 3), "t": round(float(self.broken_at[i]), 2),
                            "stressMPa": round(float(self.worst_stress[i]) / 1e6, 1)} for i in broken],
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
    c.from_ = ("the place's record of its colonies; breaking from Acropora's measured strength "
               "with an assumed branch size and contact time")
    return c


def stress_of(impulse_ns: float, height_m: float, kind: str, size_m: float) -> float:
    """The bending stress a strike puts on a colony's branches at their base, Pa."""
    force = impulse_ns / CONTACT_TIME
    lever = 0.6 * height_m
    r = BRANCH_SHARE.get(kind, 0.05) * size_m
    return force * lever / (math.pi * r ** 3 / 4.0)


class CoralSystem(System):
    name = "coral"
    reads = ("contacts", "clock")
    writes = ("coral",)

    def __init__(self, say) -> None:
        self.say = say
        self.seen = 0

    def step(self, world) -> None:
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
