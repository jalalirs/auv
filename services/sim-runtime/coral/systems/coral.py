"""The coral: colonies that stand in the vehicle's way, and break when it hits them.

Reads    contacts (what the vehicle struck this tick), the wash, the water
Writes   coral: every colony — where, how big, what kind, and what has
         happened to it

Each colony is a column of its own size standing on the seabed, which is what
the vehicle meets (systems/contact.py stops it there, as it stops it at rock)
and what the fish swim round (fishmind.py). A place lists its colonies in its
record, or — a surveyed reef of tens of thousands — draws them as one
instanced layer, and they are read back off that (`colonies_in_the_layer`).
Whoever asks what is near a point asks `near`, never every colony.
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

  **The polyps' day.** A stony coral's polyps come out to feed in the dark
  and go back in by day; a soft coral's are out by day, its algae working in
  the light (Sebens & DeRiemer 1977; Lewis & Price 1975). Any polyp goes in
  at once when it is disturbed — touched, or hit by moving water — and comes
  back out over minutes. So a vehicle working over a reef at night leaves a
  trail of closed colonies behind it, and a camera sees it. `polyps` is the
  share of each colony's polyps out, 0 to 1.

What is not here yet: the flow tearing a colony off on its own (Madin's colony
shape factor against the drag of a storm).
"""

from __future__ import annotations

import math
import pathlib

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
# The polyps. Out in the dark for stony coral, in the light for soft; in at
# once in water moving faster than DISTURBED_MS round the colony (assumed:
# polyps close to a diver's fin wash), back out over OUT_OVER_S of the day.
OUT_IN_THE_LIGHT = {"plume", "soft"}
NO_POLYPS = {"sponge"}
DISTURBED_MS = 0.08
IN_OVER_S = 3.0
OUT_OVER_DAY = 1.0 / 96.0         # a quarter of an hour of a day
POLYPS_EVERY_S = 0.5
# Sediment, mg cm⁻² a day: where harm begins, and where it is severe.
SMOTHERS_FROM = 10.0
SMOTHERS_BADLY = 50.0


class Colonies:
    """Every colony in the place, and its state."""

    # How coarse the index `near` keeps, metres.
    INDEX_M = 4.0

    def __init__(self) -> None:
        self.at = np.zeros((0, 3))          # base, world, metres
        self.size = np.zeros(0)             # how big, metres: its height, or its width if wider
        self.wide = None                    # how wide each stands, where the place says
        self.kind = np.array([], dtype=object)
        self.called = None                  # what the survey took each for, where it says
        self.prim = []                      # the drawn colony, when the place names it
        self.drawn_at = None                # where its drawn geometry stands, if not at `at`
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
        self._bends = None
        self._index = None

    @property
    def radius(self) -> np.ndarray:
        """How wide each stands, as a column: as the place drew it, or half
        its size, a little less."""
        if self.wide is not None and len(self.wide) == len(self.size):
            return self.wide
        return 0.42 * self.size

    def __len__(self) -> int:
        return len(self.size)

    def solid(self) -> np.ndarray:
        """Which colonies stop a vehicle: everything that does not bend, and
        has not been torn off and knocked over."""
        if self._bends is None or len(self._bends) != len(self):
            self._bends = np.isin(self.kind.astype(str), list(BENDS)) if len(self) else np.zeros(0, dtype=bool)
        return ~self._bends & ~self.torn_off

    def near(self, xy, reach: float) -> np.ndarray:
        """Which colonies stand within `reach` of `xy` (or of any of several
        points), by a coarse grid kept once: a reef of eighty thousand asked
        two hundred times a second cannot be asked whole."""
        if not len(self):
            return np.zeros(0, dtype=int)
        if self._index is None or self._index[0] != len(self):
            cells = np.floor(self.at[:, :2] / self.INDEX_M).astype(int)
            order = np.lexsort((cells[:, 1], cells[:, 0]))
            keys, starts = np.unique(cells[order], axis=0, return_index=True)
            ends = np.append(starts[1:], len(order))
            self._index = (len(self), {(int(a), int(b)): order[s:e] for (a, b), s, e in zip(keys, starts, ends)},
                           float(self.radius.max()))
        _, index, widest = self._index
        xy = np.atleast_2d(np.asarray(xy, dtype=float))[:, :2]
        lo = np.floor((xy.min(axis=0) - reach - widest) / self.INDEX_M).astype(int)
        hi = np.floor((xy.max(axis=0) + reach + widest) / self.INDEX_M).astype(int)
        found = [index[(a, b)] for a in range(lo[0], hi[0] + 1) for b in range(lo[1], hi[1] + 1)
                 if (a, b) in index]
        return np.sort(np.concatenate(found)) if found else np.zeros(0, dtype=int)

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
                **({} if not self.smothered.any() else self._smothering()),
                **({} if not len(getattr(self, "polyps", [])) else {
                    "polypsOut": round(float(np.mean(self.polyps)), 3),
                    "disturbed": int(np.isfinite(self.disturbed_at).sum())}),
                "from": self.from_}

    def _smothering(self) -> dict:
        """How many were smothered, over how much of the reef, and the worst.

        A count alone does not say whether a plume buried the few colonies
        under the dredger or dusted a kilometre of reef, which is the whole
        question a dredging permit asks."""
        hit = np.flatnonzero(self.smothered >= 1)
        dose = getattr(self, "dose", None)
        worst = hit if dose is None else hit[np.argsort(-dose[hit])][:5]
        return {"smothered": int(len(hit)), "smotheredBadly": int((self.smothered >= 2).sum()),
                "smotheredOver": {"from": [round(float(v), 1) for v in self.at[hit, :2].min(axis=0)],
                                  "to": [round(float(v), 1) for v in self.at[hit, :2].max(axis=0)]},
                "worstSmothered": [{"at": [round(float(c), 1) for c in self.at[i]],
                                    **({} if dose is None else {"mgCm2PerDay": round(float(dose[i]), 1)})}
                                   for i in worst]}


def as_edited(described: dict, edits, city=None) -> dict:
    """The place's colonies as its world says they are now.

    `edits` is the world's reef layer, as the claim hands it over: the coral
    items, {id, kind: "coral", form, x, y, sizeM, headingDeg, built?, prim?,
    hidden?}. A built one is a colony of the build, moved, turned, resized or
    re-formed; one not built is new, and is drawn as a copy of a built colony
    of its form; a hidden one, and a built one the world no longer lists, is
    not in the dive. Only a place that lists its colonies is edited: a reef
    drawn as a layer of tens of thousands keeps the layer, and the record says
    so rather than dropping the reef for the few the world names."""
    if isinstance(edits, dict):
        version, items = edits.get("version"), edits.get("items")
    else:
        version, items = None, edits
    if not isinstance(items, list):
        return described
    reef = dict(described.get("reef") or {})
    rows = reef.get("colonies_at") or []
    if not rows and isinstance(edits, dict) and edits.get("partial"):
        return {**described, "reef": _layer_edited(reef, edits, city)}
    if not rows:
        if items:
            reef["editsNotTaken"] = ("the place draws its reef as a layer and lists no colonies, "
                                     "so the world's coral edits are not in this dive")
            return {**described, "reef": reef}
        return described
    built = {str(r["prim"]): r for r in rows if r.get("prim") and r.get("at")}
    by_form: dict[str, list] = {}
    for r in built.values():
        by_form.setdefault(str(r.get("kind", "massive")), []).append(r)
    kept, used, copies = [], set(), 0
    for item in items:
        if not isinstance(item, dict) or item.get("kind", "coral") != "coral" or item.get("hidden"):
            continue
        if item.get("x") is None or item.get("y") is None:
            continue
        form = str(item.get("form") or "massive")
        size = float(item.get("sizeM", 0.1))
        row = {"id": str(item.get("id") or ""), "kind": form, "sizeM": size,
               "at": [float(item["x"]), float(item["y"])],
               "headingDeg": float(item.get("headingDeg", 0.0))}
        was = built.get(str(item.get("prim"))) if item.get("built") else None
        if was is not None and str(was["prim"]) not in used:
            used.add(str(was["prim"]))
            row.update(prim=was["prim"], builtAt=was["at"], builtSizeM=float(was.get("sizeM", size)))
        else:
            # New, or its prim is not in this build: a copy of the built colony
            # of its form nearest its size, or of any colony where none is.
            like = by_form.get(form) or list(built.values())
            if like:
                source = min(like, key=lambda r: abs(float(r.get("sizeM", 0.1)) - size))
                copies += 1
                row.update(prim=f"WorldCoral/{_usd_name(row['id'] or f'coral{copies}')}",
                           copyOf=source["prim"], builtAt=source["at"],
                           builtSizeM=float(source.get("sizeM", size)))
        kept.append(row)
    reef["colonies_at"] = kept
    reef["notDrawn"] = sorted(set(built) - used)
    reef["editedBy"] = {"world": version, "colonies": len(kept), "new": copies,
                        "gone": len(built) - len(used)}
    return {**described, "reef": reef}


def read_colonies(path) -> tuple[dict, dict]:
    """The header and columns of a place's colonies file (tools/reef.py
    write_colonies): row i is instance i of the reef layer, coral-<i+1>."""
    import json
    import struct

    data = pathlib.Path(path).read_bytes()
    if data[:4] != b"ICOL":
        raise ValueError(f"{path} is not a colonies file")
    (length,) = struct.unpack("<I", data[4:8])
    header = json.loads(data[8:8 + length])
    n, at = int(header["count"]), 8 + length
    columns = {}
    for name in ("x", "y", "sizeM", "builtDeg"):
        columns[name] = np.frombuffer(data, dtype="<f4", count=n, offset=at)
        at += 4 * n
    columns["form"] = np.frombuffer(data, dtype=np.uint8, count=n, offset=at)
    return header, columns


def _built_index(text, count: int):
    """coral-<n> as a row of the colonies file, or None."""
    import re
    found = re.fullmatch(r"coral-(\d+)", str(text or ""))
    n = int(found.group(1)) if found else 0
    return n - 1 if 1 <= n <= count else None


def _layer_edited(reef: dict, edits: dict, city) -> dict:
    """A reef drawn as a layer, edited by the few colonies a world names.

    A partial world lists only what was moved, turned, resized, hidden or
    copied, by coral-<n> (row n of the place's colonies file); every colony
    it does not name stays as built. The edits are taken only on the reef
    they were made on: the world carries the colonies file's digest, and a
    rebuilt reef is a different draw whose coral-<n> is another colony."""
    named = reef.get("coloniesFile")
    path = (pathlib.Path(city) / named) if city is not None and named else None
    said = {"world": edits.get("version"), "package": edits.get("package")}
    if path is None or not path.exists():
        reef["editsNotTaken"] = "the place has no colonies file, so the world's coral edits cannot be matched to it"
        return reef
    header, columns = read_colonies(path)
    # The editor names the reef it edited by the file's digest, as "digest"
    # or as the package it was edited on.
    if (edits.get("digest") or edits.get("package")) != header.get("digest"):
        reef["editsNotTaken"] = (f"the world's coral was edited on another build of this reef "
                                 f"({edits.get('package') or edits.get('digest')}); a rebuilt reef is a "
                                 "different draw, so its edits are not in this dive")
        return reef
    count, forms = int(header["count"]), list(header.get("forms") or [])
    moved, hidden, copies = {}, set(), []
    for item in edits.get("items") or []:
        if not isinstance(item, dict) or item.get("kind", "coral") != "coral":
            continue
        i = _built_index(item.get("id"), count)
        if i is not None:
            if item.get("hidden"):
                hidden.add(i)
                continue
            change = {k: float(item[k]) for k in ("x", "y", "sizeM", "headingDeg") if item.get(k) is not None}
            if change:
                moved[i] = change
            continue
        if item.get("hidden") or item.get("x") is None or item.get("y") is None:
            continue
        of = _built_index(item.get("copyOf"), count)
        if of is None:
            # Of its form, the built colony nearest its size.
            form = str(item.get("form") or "massive")
            like = np.flatnonzero(columns["form"] == forms.index(form)) if form in forms else np.arange(count)
            if not len(like):
                like = np.arange(count)
            size = float(item.get("sizeM", 0.5))
            of = int(like[np.argmin(np.abs(columns["sizeM"][like] - size))])
        copies.append({"id": str(item.get("id") or ""), "of": of, "x": float(item["x"]), "y": float(item["y"]),
                       "sizeM": float(item.get("sizeM", columns["sizeM"][of])),
                       "headingDeg": float(item.get("headingDeg", 0.0))})
    reef["layerEdits"] = {"moved": moved, "hidden": sorted(hidden), "copies": copies,
                          "builtSizeM": {i: float(columns["sizeM"][i]) for i in
                                         list(moved) + [c["of"] for c in copies]}}
    reef["editedBy"] = {**said, "partial": True, "colonies": count - len(hidden) + len(copies),
                        "moved": len(moved), "new": len(copies), "gone": len(hidden)}
    return reef


def _apply_layer_edits(c: "Colonies", edits: dict, bottom_under, which) -> np.ndarray:
    """The layer's colonies as a partial world left them: moved, sized and
    hidden in place, copies added at the end. Returns the prototype of each."""
    built = edits.get("builtSizeM") or {}
    for i, change in (edits.get("moved") or {}).items():
        i = int(i)
        if "x" in change or "y" in change:
            x, y = change.get("x", c.at[i, 0]), change.get("y", c.at[i, 1])
            c.at[i] = (x, y, float(bottom_under(x, y)) if bottom_under else c.at[i, 2])
        if "sizeM" in change:
            grown = change["sizeM"] / max(1e-6, built.get(i, change["sizeM"]))
            c.wide[i] *= grown
            c.height[i] *= grown
            c.size[i] *= grown
    add = edits.get("copies") or []
    if add:
        of = np.array([int(one["of"]) for one in add])
        grown = np.array([one["sizeM"] / max(1e-6, built.get(int(one["of"]), one["sizeM"])) for one in add])
        at = np.array([(one["x"], one["y"], float(bottom_under(one["x"], one["y"])) if bottom_under
                        else c.at[int(one["of"]), 2]) for one in add])
        c.at = np.concatenate([c.at, at])
        c.wide = np.concatenate([c.wide, c.wide[of] * grown])
        c.height = np.concatenate([c.height, c.height[of] * grown])
        c.size = np.concatenate([c.size, c.size[of] * grown])
        c.kind = np.concatenate([c.kind, c.kind[of]])
        which = np.concatenate([which, which[of]])
    keep = np.ones(len(c.at), dtype=bool)
    keep[[int(i) for i in edits.get("hidden") or []]] = False
    c.at, c.wide, c.height, c.size, c.kind = c.at[keep], c.wide[keep], c.height[keep], c.size[keep], c.kind[keep]
    return which[keep]


def _usd_name(text: str) -> str:
    import re
    name = re.sub(r"[^A-Za-z0-9_]", "_", text)
    return name if name[:1].isalpha() or name[:1] == "_" else "_" + name


def colonies_of(described: dict, bottom_under, city=None) -> Colonies:
    """The colonies a place's record lists, stood on its seabed — or, where
    it lists none and draws a reef layer, the colonies in that layer."""
    rows = (described.get("reef") or {}).get("colonies_at") or []
    layer = (described.get("layers") or {}).get("coral")
    if not rows and city is not None and layer and (city / layer).exists():
        return colonies_in_the_layer(city / layer, described, bottom_under)
    c = Colonies()
    at, size, kind, prim, drawn = [], [], [], [], []
    for row in rows:
        if not row.get("at"):
            continue
        x, y = float(row["at"][0]), float(row["at"][1])
        at.append((x, y, float(bottom_under(x, y))))
        size.append(float(row.get("sizeM", 0.1)))
        kind.append(str(row.get("kind", "massive")))
        prim.append(row.get("prim"))
        bx, by = (float(v) for v in (row.get("builtAt") or row["at"])[:2])
        drawn.append((bx, by, float(bottom_under(bx, by))))
    n = len(at)
    c.at = np.array(at, dtype=float).reshape(n, 3)
    c.size = np.array(size, dtype=float)
    c.kind = np.array(kind, dtype=object)
    c.prim = prim
    c.drawn_at = np.array(drawn, dtype=float).reshape(n, 3)
    c.height = c.size.copy()
    _fresh(c, n)
    edited = (described.get("reef") or {}).get("editedBy")
    c.from_ = (("the world's reef layer over " if edited else "") + "the place's record of its colonies; "
               "breaking from Acropora's measured strength with an assumed branch size and contact time")
    return c


def _fresh(c: Colonies, n: int) -> None:
    """Nothing has happened to any of them yet."""
    c.broken = np.zeros(n, dtype=bool)
    c.broken_at = np.full(n, np.nan)
    c.struck = np.zeros(n, dtype=int)
    c.brushed = np.zeros(n, dtype=int)
    c.worst_stress = np.zeros(n)
    c.torn_off = np.zeros(n, dtype=bool)
    c.smothered = np.zeros(n, dtype=int)
    c.polyps = np.zeros(n)
    c.disturbed_at = np.full(n, -np.inf)


def _floats(text: str, name: str, width: int) -> np.ndarray:
    """One array attribute of a USD text file, as numbers."""
    import re

    found = re.search(r"\b%s = \[(.*?)\]" % re.escape(name), text, re.S)
    if not found:
        return np.zeros((0, width))
    numbers = np.array(re.findall(r"-?\d+(?:\.\d*)?(?:e-?\d+)?", found.group(1)), dtype=float)
    return numbers.reshape(-1, width)


def colonies_in_the_layer(path, described: dict, bottom_under=None) -> Colonies:
    """The colonies a surveyed reef draws as one instanced layer
    (tools/reef-survey): where each stands, how wide and how tall.

    Every prototype is grown to a unit across and a unit high, so an
    instance's scale is its size. Which prototypes bend is the record's
    `swaysWith`; the rest are stony, and stand as massive colonies do
    (assumed: the survey says stony, head or low, not the growth form)."""
    text = pathlib.Path(path).read_text()
    at = _floats(text, "point3f[] positions", 3)
    which = _floats(text, "int[] protoIndices", 1)[:, 0].astype(int)
    scales = _floats(text, "float3[] scales", 3)
    n = min(len(at), len(which), len(scales))
    c = Colonies()
    if not n:
        return c
    at, which, scales = at[:n], which[:n], scales[:n]
    sways = (described.get("reef") or {}).get("swaysWith") or {}
    kind_of = {int(i): str(kind) for kind, ids in sways.items() for i in ids}
    c.at = at
    c.wide = scales[:, 0].copy()
    c.height = scales[:, 2].copy()
    c.size = np.maximum(2.0 * c.wide, c.height)
    c.kind = np.array([kind_of.get(int(i), "massive") for i in which], dtype=object)
    edits = (described.get("reef") or {}).get("layerEdits")
    if edits:
        which = _apply_layer_edits(c, edits, bottom_under, which)
    # What the survey took each one for (stony, head, low...), its own guess
    # from shape and colour: what a transect over the reef reports, while
    # `kind` stays what decides how a colony stands and bends.
    called = [str(one) for one in (described.get("reef") or {}).get("prototypeKinds") or []]
    if called:
        c.called = np.array([called[i] if 0 <= i < len(called) else k for i, k in zip(which, c.kind)],
                            dtype=object)
    c.prim = []
    n = len(c.at)
    _fresh(c, n)
    c.from_ = (f"the reef layer {pathlib.Path(path).name}: {n} colonies as the survey drew them"
               + (", as the world edited them" if edits else "")
               + ("" if sways else "; which bend is not recorded, so all stand as massive (assumed)"))
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
    reads = ("contacts", "clock", "light", "wash", "vehicle")
    before = ("sediment",)
    writes = ("coral",)

    def __init__(self, say) -> None:
        self.say = say
        self.seen = 0
        self._polyps_at = -np.inf

    def the_polyps(self, world) -> None:
        """Each colony's polyps towards where the day has them, and in at once
        where the water round it is moving or it was touched."""
        coral = world.coral
        if not len(coral) or not hasattr(coral, "polyps"):
            return
        now = world.clock.simulated
        if now - self._polyps_at < POLYPS_EVERY_S:
            return
        dt = POLYPS_EVERY_S if np.isfinite(self._polyps_at) else 0.0
        self._polyps_at = now
        light = float(np.clip(world.light.level, 0.0, 1.0))
        if not hasattr(coral, "_by_day"):
            kinds = coral.kind.astype(str)
            coral._by_day = np.isin(kinds, list(OUT_IN_THE_LIGHT))
            coral._none = np.isin(kinds, list(NO_POLYPS))
        want = np.where(coral._by_day, light, 1.0 - light)
        want[coral._none] = 0.0
        # Moving water round the colonies near the vehicle: the only ones its
        # wash can reach.
        near = coral.near(world.vehicle.position[:2], 4.0)
        if len(near) and world.wash.efflux.any():
            tops = coral.at[near] + np.column_stack([np.zeros((len(near), 2)), 0.5 * coral.height[near]])
            moving = np.linalg.norm(world.wash.at(tops), axis=1) > DISTURBED_MS
            coral.disturbed_at[near[moving]] = now
        hits = world.contacts.coral_hits
        touched = [int(h["colony"]) for h in hits[getattr(self, "_touches_seen", 0):]]
        self._touches_seen = len(hits)
        if touched:
            coral.disturbed_at[touched] = now
        shut = (now - coral.disturbed_at) < 5.0
        want[shut] = 0.0
        if dt <= 0.0:
            coral.polyps = want.copy()
            return
        day = max(float(getattr(world.light, "day_s", 86400.0)), 1.0)
        going_in = want < coral.polyps
        rate = np.where(going_in, dt / IN_OVER_S, dt / (OUT_OVER_DAY * day))
        coral.polyps += (want - coral.polyps) * np.clip(rate, 0.0, 1.0)

    def judge_the_sediment(self, world) -> None:
        _judge(world.coral, world.sediment.on_coral_mg_cm2, world.clock.simulated, self.say)

    def step(self, world) -> None:
        self.judge_the_sediment(world)
        self.the_polyps(world)
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


# Each smothered colony is said by name up to this many; past it, how many
# and where, at most once a SMOTHERING_SAID_EVERY_S. A dredging dive said all
# 93,598 by name, and the record kept the names and lost the dive's ending.
SMOTHERED_BY_NAME = 25
SMOTHERING_SAID_EVERY_S = 60.0


def _judge(coral, settled, seconds, say):
    """Smothering, from the dose: once a level is passed, said once."""
    if settled is None or len(settled) != len(coral):
        return
    dose = dose_per_day(np.asarray(settled), seconds)
    coral.dose = dose
    level = np.where(dose >= SMOTHERS_BADLY, 2, np.where(dose >= SMOTHERS_FROM, 1, 0))
    worse = np.flatnonzero(level > coral.smothered)
    if not len(worse):
        return
    named = getattr(coral, "named_smothered", 0)
    for i in worse[:max(0, SMOTHERED_BY_NAME - named)]:
        say("coral_smothered", colony=int(i), growth=str(coral.kind[i]),
            mgCm2PerDay=round(float(dose[i]), 1), badly=bool(level[i] >= 2))
    coral.named_smothered = min(SMOTHERED_BY_NAME, named + len(worse))
    coral.smothered[worse] = level[worse]
    if named + len(worse) > SMOTHERED_BY_NAME and \
            seconds - getattr(coral, "smothering_said_at", -np.inf) >= SMOTHERING_SAID_EVERY_S:
        coral.smothering_said_at = seconds
        say("coral_smothering", **coral._smothering())
