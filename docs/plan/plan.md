# The plan

The list in `todo.md` is sixty-six items and it is a backlog: everything anybody
noticed, in the order they noticed it. This is different. This is the subset
that turns what exists into something a reef programme could use, in the order
it can be built, with what "done" means for each part written down before it is
started rather than after.

Most of the backlog is not in here. That is the point of a plan.

---

## What is being built

**A reef programme rehearses a mission before it spends ship time.**

They open their reef. They lay out the site the way it will really be — the
array where it will be laid, the ship where it will hold, the nursery frames
where they are. They build the mission over it. They ask what could go wrong,
and the answer comes back overnight as a sentence somebody can act on:

> Survives 142 of 180. Every failure is current above 0.35 m/s from the
> north-east. Flying the lanes north–south recovers 31 of them. Allow eleven
> days of ship time for seven days of work.

Everything below exists to make that paragraph true and to put it on a screen.

## What is deliberately not in this plan

Named, so that nobody has to wonder whether they were forgotten: more than one
vehicle in the water (65), the rest of the fleet beyond publishing what already
exists (51, 55), time of day and tide and season (61), export to other people's
tools (60), ground finer than the survey (58), sensors beyond what is already
declared (56, except the two the plan does need), the benchmark's own screen
(37), and a glider beyond what it already does.

All of them are real and none of them is load-bearing for the paragraph above.
They go back on the list when it is true.

---

# Stage 1 — Make what exists trustworthy and worth looking at

Nothing here is new capability. It is the debt that will otherwise be paid at
the worst moment, and it is four things that are already understood.

### 1.1 A run says what computed it *(todo 59)*

The record pins the place, the vehicle and the conditions by digest and nothing
about the simulator. Physics changed six times in one day and every result from
before became incomparable with every result after, silently.

- `contracts`: a run gains `runtime`, carrying the sim image digest and a
  `physics` integer that the runtime itself declares.
- `sim-runtime`: a single constant, bumped by hand when behaviour changes, and
  written into the settled event. The number is not clever and does not need to
  be: what matters is that it changes when the answer would.
- `control-plane`: stored on the run, returned with it.
- `tools/what-if` and any table of results: refuse to put two physics versions
  in one comparison without saying so.

**Done:** two runs from either side of a bump cannot be tabulated together in
silence.

### 1.2 The reef stops looking wrong *(todo 50)*

The seabed is surfaced with a satellite photograph, which has already been
through fifteen metres of water; the renderer attenuates it again and the ground
goes black under lit coral. Taking the water out is done and is not enough —
red is gone in four metres and there is nothing there to recover.

- `tools/zonation.py`: classify the bottom from the two bands that survived —
  sand, rubble, pavement, coral — rather than only deriving how much coral.
- `tools/make-site`: colour each class from a reference table, modulated by the
  imagery's own brightness so the structure is kept and the cast is not.
- Rebuild and republish Al Fahal; pull frames from a dive and compare.

**Done:** a frame from a reef dive reads as a reef.

### 1.3 A model flies a dive *(todo 49)*

Built, wired, never run, because the agent could not be redeployed while a sweep
was in the water. The water is empty now.

- `./tools/box up`, then a survey over Al Fahal with `flyWith: "asking"`.
- Whatever comes back — a good plan, a refused one, or nothing — goes in the
  record and in the item.

**Done:** the record contains a dive whose plan a model wrote.

### 1.4 The application stops lying about itself *(todo 63, first half)*

- Delete the Conditions and Recordings tabs. Conditions belong to a mission or
  a sweep; a recording belongs to the dive that made it.
- Leave Sweeps, but greyed, with a date — it becomes real in stage 4.
- Rebuild Autonomy as what each controller has *done* rather than what has been
  uploaded: flown, scored, cost, over which tasks. Deploying is a button on
  that page, not its subject.

**Done:** no tab is grey without a reason written next to it.

---

# Stage 2 — A place somebody arranged

The largest stage and the one everything after depends on. Built as a thin
vertical slice first: **one tool, all the way through**, then widen.

### 2.1 A layout is a thing the platform keeps

Reuse what already works rather than inventing a second versioning system: a
layout is a versioned asset belonging to a city, digested and pinned exactly
like a package.

- `contracts`: `Layout` — a city, a name, and a document of things. A dive
  gains `layoutVersionId`, nullable.
- `control-plane`: the same catalogue machinery cities and vehicles already
  use, so pinning, granting and refusing-to-change-a-published-thing come free.
- The document: each thing carries a kind, a position in site metres, and the
  depth its landing rule resolved to — **resolved when it is drawn, not when it
  is flown**, so a layout means the same thing whatever reads it.

### 2.2 The runtime knows what is in the water

- `sim-runtime`: read the layout beside the place, draw its things in the
  scene, and hold them as truth the way item 25 already holds a search target.
- Collision against them, using the same two constraints `land()` uses for the
  ground — this is the half of it that makes an obstacle an obstacle.

### 2.3 The editor, one tool deep

- The place page lists its layouts; one opens the editor.
- The chart is the place's own heightfield, shaded by depth, with the depth
  under the cursor.
- **Transponders only**, to begin with: place, select, move, delete,
  duplicate, save.
- The mockup at `claude.ai/code/artifact/72da3414` is the design; the palette
  grouped by how a thing meets the bottom is the part to keep.

### 2.4 Prove the chain

Lay an array by hand, save it, fly a dive that pins it, and confirm the vehicle
took its fixes from transponders that are where they were drawn.

**Done:** place → layout → dive → record holds, with one tool.

### 2.5 Then widen

Each of these is an afternoon once 2.1 to 2.4 hold, and each is a landing rule
and a glyph: mooring block, nursery frame, ship with USBL, marker buoy, mooring
line, marker post, restoration cell. The line is the only one with real work in
it, because it spans two points and hangs between them.

---

# Stage 3 — A mission somebody keeps

### 3.1 Geometry moves out of the task *(todo 57)*

Today a task carries its own geometry as offsets from wherever the vehicle
happened to start, because there is nowhere else for geometry to live. Now
there is.

- `sim-runtime/tasks.py`: a task may name a thing in the layout instead of
  giving `dx`/`dy` — `{"over": "cell-b7"}` rather than a width, a height and a
  spacing. The existing forms keep working; nothing already written breaks.
- The scoring rules do not change at all. This is where the work goes and it is
  not where the risk is.

### 3.2 A mission is a resource

- `contracts`: `Mission` — a place, a layout, and an ordered list of stages,
  each a task kind and what it is over. The `mission` task kind already
  sequences stages; this gives it somewhere to live.
- `control-plane`: create, list, version, pin.
- A dive is composed *from* a mission rather than by rebuilding one.

### 3.3 The Missions tab

List, open, build over a layout, save. The dive page picks one instead of
assembling an objective from nothing.

**Done:** a mission written once is flown twice by two people and the two runs
are comparable.

---

# Stage 4 — The rehearsal

The product. Most of the engine exists in `tools/what-if`; what it has never
had is somewhere to live and a screen.

### 4.1 A sweep is a resource

- `contracts`: `Sweep` — a mission, a doubt list, a threshold. A run gains the
  sweep and the scenario it belongs to.
- `control-plane`: submit the cross product as a batch, report progress.
- The analysis moves out of the tool and into the platform, unchanged: ranked
  by what *changes* the outcome, indifferent dimensions named once and not
  ranked.

### 4.2 What it costs *(todo 66)*

Every input is already in the record and nobody has asked it for anything.

- Dives per charge, from energy against capacity and reserve.
- Cells per day, from how long one took.
- Days lost, from the share of scenarios that failed.
- Reported as ship days and dives, not as a fraction.

### 4.3 The Sweeps tab

Define the doubts, watch it fly, read the answer. The answer is a paragraph and
a small table, not a grid of numbers — the grid was tried and nobody could read
it.

**Done:** somebody who has never opened a terminal lays out a site, builds a
mission, sweeps it, and is told what to do about Tuesday.

---

# Stage 5 — Doubts that are about the world

Only now, because none of it can be asked before there is a world to doubt.

### 5.1 The tether *(todo 53, first part)*

Out of order in the backlog on purpose and pulled forward here for the same
reason: it needs nothing above, and it is the only thing in the plan that is
already **wrong** rather than absent. A hundred metres of tether streaming in a
current has more area than the vehicle and is often the larger force; every
tethered dive in the record flew without it.

- `hydrodynamics`: tether drag as a term on the vehicle, from length streamed,
  the current, and where the surface end is.
- The surface end is a thing on the layout — which is why it sits here and not
  in stage 1.

### 5.2 Things where the chart does not say

- Lines bow with the current. Quasi-static catenary, no solver.
- The doubt list gains structural entries: *the mooring is thirty metres from
  where it was laid*, *the array has one transponder down*, *there is a net
  where the chart says clear water*.

### 5.3 The sonar becomes a sensor *(todo 56, first part)*

Declared in the package since the beginning and returning nothing, because
there has been nothing to return off. Now there is.

**Done:** a sweep can ask what happens if the world is not as drawn, and answer.

---

# How this is actually run

**Vertically, never by layer.** Every stage above ends in something flown and
looked at. A stage that ends in a passing test and nothing flown is not done.

**The record is cleared before each stage that changes physics,** and the
physics version (1.1) is what says whether that was necessary.

**Two devices.** A sweep of seventy-two scenarios takes most of a day on this
box, and stages 4 and 5 both end in sweeps. That is the pacing constraint on
the whole plan and no amount of planning moves it — what moves it is more
devices or shorter missions, and shorter missions is the one that is free.

**What would make this plan wrong.** Somebody who dives looking at stage 1.2 and
saying the reef still looks wrong; a layout that cannot be drawn in under five
minutes in stage 2.3; a sweep in stage 4 whose answer nobody acts on. Each of
those is worth stopping for, and none of them is discoverable from here.
