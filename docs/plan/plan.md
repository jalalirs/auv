# The plan

The previous version of this file was a feature sequence with an engineering
plan's name on it, and it had the fault that names one: work in its first stage
would have been unpicked by its third. This one starts from the code.

Everything below was read before it was written. The findings are specific, the
refactors come before the features that need them, and nothing is built twice.

---

# Part I — What the code actually is

## The catalogue is half generalised, and stopped

`internal/catalog` already treats a **version** as generic. `AssetKind`,
`Version`, `CreateVersion`, `publishVersion`, `grantAsset` and `listVersionsOf`
all take the kind as a parameter and do not care what it is. That half is
finished and it is good.

The **asset** half is not. `CreateCity`, `City`, `CityBySlug`, `Cities` exist,
and beside them `CreateVehicle`, `Vehicle`, `VehicleBySlug`, `Vehicles`, the
same shape written twice. In `httpapi/catalog.go` the same split: `grantAsset`,
`createVersion`, `listVersionsOf` are generic; `listCities`, `createCity`,
`readCity`, `grantCity`, `readCityGrants`, `revokeCityGrant` are per kind, and
so are their six vehicle twins.

Somebody generalised the hard half and left the boring half. That is fine for
two kinds. **This plan adds three more** — layout, mission, sweep — and at two
kinds the duplication is invisible, at five it is the shape of the codebase.

## `Dive` in the runtime is a god class

`sim-runtime/coral/runner.py` is 2,005 lines and `Dive` has **fifty-nine
methods**. Reading them, the seams are already there and unmarked:

  loading a USD scene and finding the water in it; the water's own properties;
  the task and what it is scored against; navigation and what the vehicle
  believes; the physics step, the ground, the surface; the recording and what
  is said; energy; the ROS bridge; the coral; manual control.

Every feature in Part III puts things in the water — objects, a tether, lines
that move — and every one of them lands on this class. Adding them as they are
makes it seventy methods and nobody will ever take them out again.

## `tasks.py` is one file with every task in it

1,693 lines. Adding "a task may point at something drawn on a layout" touches
all of them, and the file is already the one nobody wants to open.

## `dive` in the control plane already holds most of what a sweep needs

`internal/dive` carries Stack, **Conditions**, Dive and Run. Conditions is
already a stored, named, reusable resource — so removing its tab from the
application removes a tab, not a model, which is the cheap direction.

## The client has screens and no structure between them

Flat files under `screens/`, `Dive.tsx` at 432 lines composing a dive inline
from six catalogues. There is no place for a new tab to be added that is not
"another file in the folder", which is exactly how the three grey tabs happened.

---

# Part II — The target, and the refactors that get there

Each refactor below is behaviour-preserving, testable on its own, and is done
**before** the feature that needs it. None of them is optional and none of them
is interesting on its own, which is why they have to be scheduled rather than
hoped for.

## R1 · Finish the asset generalisation *(control plane)*

**Why first:** three of the four features in Part III add an asset kind. Doing
them on the current shape means writing the six-handler wrapper three more
times and then unpicking eighteen functions later.

**What:** an asset becomes a descriptor rather than a copy —

    type Asset struct {
        Kind      AssetKind        // city | vehicle | layout | mission | sweep
        IDPrefix  ids.Kind
        Owns      []AssetKind      // a layout belongs to a city
        Extra     func() any       // what this kind carries beyond name and slug
    }

`Store.CreateAsset/Asset/AssetBySlug/Assets` over the descriptor; the city and
vehicle functions become three-line calls kept for their callers. In `httpapi`,
`listAssets(kind)`, `createAsset(kind)`, `readAsset(kind)` and one route
registration loop.

**How we know it worked:** the existing contract tests pass untouched, and the
city and vehicle endpoints answer byte-identically. Nothing else changes.

**Not in scope:** the dynamics endpoint, which is genuinely vehicle-only.

## R2 · Break `Dive` into the things it is made of *(sim runtime)*

**Why before Part III:** objects, collision, a tether and things that move all
land here. On the class as it stands they land as methods fifty-nine through
seventy.

**What:** the seams the method groups already show —

  `scene.py`    — opening a place, its layers, the water level, where a dive
                  begins. Owns USD; nothing else imports `pxr`.
  `sea.py`      — the water: current, density, temperature, visibility, and
                  what the conditions said. Already nearly separate.
  `world.py`    — **new**: what is in the water besides the vehicle. Empty at
                  first, and the home for everything in Part III.
  `vehicle.py`  — the body, the step, the ground, the surface, energy.
  `mission.py`  — the task, what it is scored against, the plan it was given.
  `record.py`   — what is said, what is recorded, what the result is.
  `runner.py`   — what is left: a `Dive` that owns those six and runs a loop.

**How we know it worked:** all 193 tests pass with no test changed. That is the
whole check and it is a strong one — they cover physics, tasks, navigation,
energy, surfacing and the glider.

**Done in one pass, not gradually.** A half-split class is worse than either.

## R3 · Tasks become a package, and geometry becomes a reference *(sim runtime)*

**Why here:** it is the same edit to every task, and doing it before missions
exist means missions land on a task layer that already accepts references.

**What:** `tasks/` with a module per family, and one change to the base — a task
may be given `{"over": "<thing in the layout>"}` where it now takes `dx`/`dy`.
The existing forms keep working; every scoring rule is untouched.

**How we know:** existing task tests pass unchanged; new ones cover references.

## R4 · The application gets an information architecture *(client)*

**Why before any new screen:** three tabs were added without one and all three
were still grey weeks later.

**What:** a declared navigation — every tab a record of what it is, what it
lists, and what it opens — so a new one is data and not another file in a
folder. Then the deletions and the Autonomy rebuild are the first two things
expressed in it rather than one-off edits.

---

# Part III — What is built, on top of that

The order is forced by the dependencies and each stage ends in something flown
and looked at.

## Stage A · Trust and appearance

Nothing new; everything already understood. **Depends on R1 for the migration,
R4 for the deletions.**

- **A1 A run says what computed it.** `runtime` on the run: the sim image
  digest and a physics version the runtime declares. Done in the *same*
  migration and the same contract change as the sweep fields in stage D, so the
  run record is altered once — this is the specific thing the previous plan got
  wrong.
- **A2 The reef stops looking wrong.** Classify the bottom from the bands that
  survived; colour from the class, not from the photograph. Republish, fly,
  compare frames.
- **A3 A model flies a dive.** One deploy, one dive, whatever it says.
- **A4 Delete Conditions and Recordings; rebuild Autonomy as a comparison.**
  The first thing built on R4.

## Stage B · A place somebody arranged

**Depends on R1 (layout is an asset kind), R2 (`world.py` is where its things
live).**

- **B1** `Layout` as an asset kind — no new CRUD, it is a descriptor.
- **B2** The layout document: things with a kind, a position, and the depth
  their landing rule resolved to **when drawn, not when flown**.
- **B3** `world.py` reads it, draws it, holds it as truth, and collides with it
  using the constraints `land()` already applies to the ground.
- **B4** The editor, **transponders only**, on R4's navigation: place, select,
  move, delete, duplicate, save.
- **B5** Fly a dive that pins a layout and takes fixes from an array that is
  where it was drawn. *This is the proof of the whole chain.*
- **B6** Then the rest of the palette, one landing rule each.

## Stage C · A mission somebody keeps

**Depends on R1, R3, and B.**

- **C1** `Mission` as an asset kind: a place, a layout, ordered stages.
- **C2** Stages name drawn geometry, which R3 already accepts.
- **C3** The Missions tab; the dive page composes from a mission instead of
  rebuilding one.

## Stage D · The rehearsal

**Depends on C. Uses the run fields already added in A1.**

- **D1** `Sweep` as an asset kind: a mission, a doubt list, a threshold.
- **D2** The cross product submitted as a batch; the analysis moved out of
  `tools/what-if` unchanged.
- **D3** What it costs — ship days, dives, battery swaps. Every input is
  already in the record.
- **D4** The Sweeps tab, which stops being grey.

## Stage E · Doubts about the world

**Depends on B3 for a world to doubt, R2 for somewhere to put it.**

- **E1 The tether.** Drag as a term on the vehicle, with its surface end a
  thing on the layout. The only item in the plan that is already *wrong*.
- **E2** Lines bow with the current; the doubt list gains structural entries.
- **E3** The sonar returns off what is there.

---

# Part IV — How this is kept honest

**Nothing is touched twice, and here is where that was at risk.** The run
record: altered once, in A1, carrying both provenance and the sweep fields that
stage D needs. The navigation: declared once in R4 before any tab is added or
removed. The asset CRUD: generalised in R1 before three kinds are added to it.
Those three were the rework in the previous plan and they are the reason this
one has a Part II.

**A refactor that changes behaviour has failed.** R1 and R2 are checked by
existing tests passing untouched — 193 of them, covering the parts that are
hard to get right. If a test has to change, the refactor was a rewrite wearing
a refactor's name, and it stops.

**Every stage ends in a dive.** Not a passing test — something flown and looked
at. A stage that ends green and unflown is not done.

**The record is cleared when physics changes,** and after A1 the platform can
say whether that was necessary rather than guessing.

**Two devices.** Stages D and E end in sweeps and a sweep of seventy-two
scenarios takes most of a day on this box. That is the pacing constraint on the
back half of the plan; the free lever is shorter missions, not more planning.

**What would show this plan is wrong:** somebody who dives saying A2 still
looks wrong; a layout that cannot be drawn in five minutes at B4; a sweep at D4
whose answer nobody acts on. None is discoverable from here, and each is worth
stopping for.
