# The plan, end to end

From the code as it is today to a platform a reef programme uses. One sequence.
Restructuring appears where the work needs it and not as a phase of its own,
because a refactor nobody is about to build on is a refactor nobody finishes.

Every step says what changes, which files, why it is in that position, and how
we know it worked. Every step ends in something that runs.

**The target, so every step below can be checked against it.** Somebody opens
their reef, lays out the site the way it will really be, builds the mission over
it, asks what could go wrong, and reads this in the morning:

> Survives 142 of 180. Every failure is current above 0.35 m/s from the
> north-east. Flying the lanes north–south recovers 31 of them. Allow eleven
> days of ship time for seven days of work.

---

## 1 · A model flies a dive

`./tools/box up`, then one survey over Al Fahal with `flyWith: "asking"`.

First because it is one command and because until it happens the claim that this
platform has an AI controller is an assertion. Built, wired, tested for the
arrangement, never once run — the agent could not be redeployed while a sweep
was in the water, and the water is empty now.

**Done:** a dive in the record whose plan a model wrote, and the item in
`todo.md` says what came back.

*Done (14 September).* MiniMax-M3 flew a survey over Al Fahal: `flownBy
{"asking": 1.0}`, seven plans, no failures, 106.6 m flown, 15.5% of the cell.

The grant did not work the first time and the reason was worth having. The
worker set `Network: true` and the diver also set `Attach` to the dive's own
network, and in `createRequest` those were written as alternatives — `if
spec.Attach != "" { network = spec.Attach }` — so the grant silently did
nothing. The container could not resolve a hostname and the controller sat
there with nothing to ask. They are not alternatives: a dive that is granted a
route out gets a **second** network added beside the sealed one, which is also
the better security shape. The simulator is ours and may ask a model; the stack
flying it is somebody else's code on our machine and still reaches nothing.

Two things the first real model dive found, both fixed:

  **Patience was twenty seconds and the model takes twenty-five.** Five of
  seven plans were thrown away by a stopwatch chosen before anything real had
  ever been asked a question, and the dive read as a controller that could not
  plan. A controller now says how long it needs; `asking` says two minutes,
  inside its own request timeout.

  **The record credited the wrong planner.** `flownBy` said the model and
  `plannedBy` said "the platform's planner", because `asking` never set it. A
  controller that plans for itself is now believed over what was written when
  the task was set.

## 2 · The reef stops looking wrong

`tools/zonation.py`, `tools/make-site`, then republish Al Fahal.

Independent of everything else, visible immediately, and the thing anybody
shown this platform reacts to first. The seabed is currently surfaced with a
satellite photograph that has already been through fifteen metres of water; the
renderer attenuates it again and the ground goes black under lit coral.

Taking the water back out is done and is not enough — red is gone in four metres
and there is nothing left to recover. So the two bands that survived classify
the bottom (sand, rubble, pavement, coral) and the class carries the colour,
modulated by the picture's own brightness so structure is kept and the cast is
not.

**Done:** frames pulled from a dive over the reef read as a reef.

*Done (14 September).* The seabed was surfaced with the satellite photograph
and came out at RGB 30, 77, 81 — light that had already been down through
fifteen metres of water and back, attenuated a second time by the renderer.
It is now 166, 157, 132: sand, rubble and pavement, classified from the two
bands that survived and coloured by what each of them is, with the picture's
own brightness kept as grain so the reef has metre-scale variation without its
cast coming back. Published as Al Fahal v2.

## 3 · The application gets somewhere to put a tab

`apps/client/src/renderer/` — a declared navigation before any screen is added
or removed.

Here, not later, because the next four steps each add a screen and three tabs
have already been added without this and sat grey for weeks. A tab becomes a
record — what it is, what it lists, what it opens — so adding one is data rather
than another file in a folder.

Then the two things that are already decided, expressed in it: **delete
Conditions and Recordings** (water belongs to a mission or a sweep; a recording
belongs to the dive that made it), and **rebuild Autonomy** as what each
controller has flown, scored and cost rather than what has been uploaded.

**Done:** no tab is grey without a reason beside it, and Autonomy answers a
question somebody has.

*Done (14 September), and smaller than planned.* The navigation was already a
declared array — `PAGES` and `LATER` in `Deck.tsx` — so there was nothing to
build, only something to use. Conditions and Recordings are gone, with the
reason written where they were: water belongs to the thing it is water for, and
a recording belongs to the dive that made it. Sweeps stays, greyed, with a
description that now matches what step 16 will build. Typecheck clean.

## 4 · Assets stop being written out per kind

`internal/catalog/catalog.go`, `internal/httpapi/catalog.go`, `routes.go`.

Here because the next step adds an asset kind and two more follow it. The
version half is already generic — `Version`, `CreateVersion`, `publishVersion`,
`grantAsset`, `listVersionsOf` all take the kind and do not care. The asset half
is not: `CreateCity/City/CityBySlug/Cities` with four identical vehicle twins,
and six per-kind HTTP handlers each.

At two kinds that duplication is invisible. At five it is the shape of the
codebase, so it is finished now rather than copied three more times and unpicked
later. An asset becomes a descriptor — its kind, its id prefix, what owns it,
what it carries beyond a name — and the city and vehicle functions become
three-line calls that keep their callers working.

**Done:** the existing contract tests pass untouched and the city and vehicle
endpoints answer identically. A behaviour change here is a failure, not a
feature.

*Done (14 September), and narrower than planned.* Reading the code rather than
the plan, the duplication was not what this step assumed. The **inserts and the
scanners are genuinely per kind** — a layout is not a city and forcing them into
one descriptor would have cost more than it saved. What was duplicated was
exactly three things, written once per kind and identical in SQL modulo the
table: read by id, read by slug, and list what a subject may see.

So `catalogued[T]` carries those three and nothing else, and City and Vehicle
keep their own inserts and their own columns. Six functions became six
one-liners over one implementation. The check was the endpoints: six cities,
two vehicles, by id, by slug, with versions, all answering as before.

## 5 · A layout is a thing the platform keeps

`internal/catalog` (a descriptor, no new CRUD), `packages/contracts`,
`internal/dive` for the dive's reference to one.

A layout is an arrangement *of a place*: versioned, digested and pinned exactly
as a package is, because a mission flown over an array is only repeatable if the
array is pinned as hard as the reef. A dive gains a nullable
`layoutVersionId`.

The document is a list of things, each with a kind, a position in site metres,
and **the depth its landing rule resolved to at the moment it was drawn** — not
at the moment it is flown. A layout then means the same thing to the editor, the
runtime and the record, and re-flying one in September gets the site from March.

**Done:** a layout can be created, published, pinned and read back, and a
published one cannot be changed.

## 6 · The runtime knows what is in the water

`sim-runtime/coral/world.py` — new — and the smallest possible cut into
`runner.py`.

`Dive` is 2,005 lines and fifty-nine methods. It is not being split up here,
because a refactor done in front of a feature that needs it is worth doing and
one done on principle is worth arguing about. What comes out is exactly the part
this step needs: **what is in the water besides the vehicle**. It reads the
layout beside the place, draws its things, holds them as truth the way item 25
already holds a search target, and collides with them using the same two
constraints `land()` applies to the ground.

Everything later in this plan that puts something in the sea lands in `world.py`
rather than becoming methods sixty through seventy.

**Done:** a dive over a place with a layout has the layout's things in it, and a
vehicle driven at one stops.

## 7 · The editor, one tool deep

`apps/client/src/renderer/screens/` on step 3's navigation.

A place opens to its own page, that page lists the layouts made of it, and one
opens the editor. The editor is not a tab: a layout is an arrangement of
somewhere and means nothing detached from the ground it was drawn on.

**Transponders only.** The chart is the place's own heightfield shaded by depth,
with the depth under the cursor; place, select, move, delete, duplicate, save.
The design is the mockup already made — the palette grouped by *how a thing
meets the bottom*, because that is the only part the editor has to resolve.

One tool, because the chain matters more than the palette.

**Done:** somebody lays an array by hand and saves it.

## 8 · Fly what was drawn

No new code. An array laid by hand in step 7, a dive that pins it, and the
vehicle taking fixes from transponders that are where somebody put them.

This is the proof of the whole chain — place, layout, dive, record — and it is a
step rather than a check because if it does not hold, steps 5 to 7 are wrong and
everything after them is built on it.

**Done:** a dive in the record names both a place and an arrangement of it.

*Done (14 September).* A four-transponder array laid on a 300 m square round
the reef Al Fahal says a dive begins at — each one resting on the bottom it was
drawn over, 12.1 m to 16.1 m, because the ground under that square is not flat.
One dive inside it, one 420 m outside it, both pinning
`ver_01M2G3F6Z388WWH35ZCN8ZDFT3`. Inside: 72 fixes, `an LBL fix from 4
transponders`, 0.26 m of drift. Outside: no fixes at all, 2.1 m of drift over
89 m flown. The arrangement decides where the vehicle knows where it is, which
is the whole claim.

It was not the no-new-code step it says it is, and both reasons were the same
mistake in two places — a frame nobody had written down.

  **An array was a circle, not its transponders.** `navigation.py` modelled LBL
  as one point with a radius, so a layout full of transponders changed nothing:
  the vehicle got fixes from a circle round wherever it launched. An array's
  reach is not a circle — at the edge you lose the far side first, and the
  fixes stop before you have left the middle of anything. A fix now needs three
  of the drawn transponders in range, which is what cutting a position takes.

  **The editor and the water disagreed about which way north is.** The
  heightfield runs south to north, which the site's own note says and the
  runtime reads that way; the editor read it as an image with row zero at the
  top, so every depth it resolved came from the mirrored latitude. It also drew
  in metres from the south-west corner while everything else in a dive is
  metres from the middle, so a thing drawn in the centre of the chart would have
  been laid at the north-east corner of the site. Both are gone, and the
  document now *says* its frame instead of leaving three readers to guess it.

## 9 · The rest of the palette

`world.py`, the editor, and a landing rule each.

Now that the chain holds, each of these is an afternoon: mooring block, nursery
frame, ship with USBL, marker buoy, marker post, restoration cell. The mooring
line is the only one with real work in it, because it spans two points and hangs
between them rather than sitting on one.

**Done:** a site can be laid out the way it will really be.

*Done (14 September).* Eight kinds: transponder, mooring block, nursery frame,
marker post, buoy, ship, mooring line, restoration cell. Al Fahal's restoration
plot laid with twelve of them — a 60 × 40 m cell, posts on its corners, three
frames inside it, a mooring, and a ship holding station 90 m north — and flown
three times. The record of every run now carries what it was flown through.

Four things it settled, three of which were one class of mistake: a shape that
was really three shapes wearing one set of fields.

  **`Thing` became three.** Something standing at a point, something spanning
  between two, and an area drawn on the chart. One class with flags would have
  been one class needing a fourth flag next month; `Thing.of()` picks the shape
  from the kind's landing rule and nothing outside the module asks which it
  got.

  **A ship's three metres were three metres of sky.** The vertical extent ran
  upward from wherever a thing was landed, which is right for a post and
  exactly wrong for a hull: a vehicle at two metres deep flew through the only
  part of a ship that is in the sea. Surface things now hang down.

  **A slack line is not where the straight line is.** A mooring line is the one
  kind that is not anywhere — it is everywhere along a curve. Solved as a real
  catenary rather than drawn as a chord: over a hundred metres, five per cent
  of slack puts the middle 13.9 m below its ends, against 13.7 m from the
  shallow-sag approximation, and the solver reproduces the asked arc length to
  a centimetre. A vehicle flown at the chord's depth at mid-span meets nothing;
  one flown 14 m lower meets the line.

  **The ship carries the transceiver.** USBL took its fix from straight
  overhead, which is the best case and never quite true. With a ship drawn, the
  fix comes from where the ship is and its error is a share of *that* slant
  range — 91 m from the vehicle rather than 12 m of depth — and the record says
  how far it came.

Two smaller ones the flying found: a `reach` target written as `[x, y, z]`,
which is how every other position in the record is written, fell through to
"twenty metres ahead of wherever you started" and flew a different dive without
saying so; and a strike reported itself once per physics step, which is four
hundred events for four seconds against a frame. Flown straight at a nursery
frame, the vehicle is now stopped at its edge, says so once, goes round, and
arrives with the detour visible in the score: directness 0.966 instead of 1.

## 10 · A task can point at something drawn

`sim-runtime/coral/tasks.py` → `tasks/`, a module per family.

Split here because this is the edit that touches every task, and doing both at
once means opening the 1,693-line file once instead of twice.

The change to the base is one thing: a task may be given `{"over": "cell-b7"}`
where it now takes `dx` and `dy`. The existing forms keep working. **No scoring
rule changes** — that is where the work is and it is deliberately not where the
risk is.

This is what makes a drawn site worth drawing: until now a task carries its own
geometry as offsets from wherever the vehicle happened to start, because there
is nowhere else for geometry to live.

**Done:** existing task tests pass unchanged; a task scores against a cell
somebody drew.

*Done (14 September).* 1,699 lines became a package of five, grouped by what
the score means rather than by anything alphabetical: `going` is a position and
a tolerance, `covering` is a fraction of something, `working` is a count of
things, `mission` is several of those in sequence, and `base` is what they
share. Every task file was moved whole — no rule was retyped, and the 33
existing task tests passed unchanged before anything new was added.

Two things went while the file was open, both the same shape of problem:

  **`task_for` knew each task's constructor.** A chain of `if made is Survey`,
  `if made is Monitor` — which is a chain the eighteenth task has to find and
  add itself to. Each class now says `wants = ("camera",)` and the builder
  hands over what was asked for.

  **Subclasses swallowed what they did not understand.** Every `__init__`
  forwards `**extra` to the base now, so a new thing the base needs — the
  world, today; a scenario, at step 13 — reaches all seventeen tasks without
  touching seventeen signatures.

Then the step itself: `{"over": "cell-b7"}` anywhere a task takes a point, and
a survey pointed at a plot takes the plot's own extent. Flown on Al Fahal's
drawn cell, the survey ran the plot's 60 × 40 m rather than a box ahead of
wherever the vehicle happened to be aimed, and the result names what it was
pointed at. **No scoring rule changed** — what changed is where the geometry
comes from.

The part worth keeping is the failure. A dive pointed at `cell-b7` in a place
where nobody drew a `cell-b7` is refused before it flies, and the refusal lists
what *is* in the water. It would otherwise have fallen back to a box ahead of
the vehicle and come back as a score of 0.2 — which reads as a controller that
flew badly, and is the most expensive kind of wrong a simulator can be.

## 11 · A mission is a thing you keep

`internal/catalog` (another descriptor), `internal/dive`, `packages/contracts`.

A mission is a place, a layout of it, and an ordered list of stages — each a
task kind and what it is over. The `mission` task kind already sequences stages;
this gives it somewhere to live other than inside one dive, where it currently
dies.

**Done:** a mission written once is flown twice by two people, and the two runs
are comparable because both pin the same three things.

*Done (14 September).* "Al Fahal, the September plot round" — survey the drawn
plot, read the middle nursery frame, come home — written once and flown by two
people who each supplied nothing but a name, a vehicle and the water. Both
dives came back pinning the same place, the same arrangement and the same
stages, and the difference between their results is the flying.

A mission turned out to be a layout with a different document in it, so it is
built that way: **one descriptor serves both.** `madeOfAPlace` in the store,
one set of five handlers in the API, one `MadeOfAPlace` record with a `kind`.
Writing the second out by hand would have been sixty lines of the first with a
word changed, and the third would have been sixty more.

Four things the flying found, and the first is the one that matters:

  **Every mission dive had been silently scoring zero.** `Mission.step` was
  written without `believed` while the base grew it, so the runner's call
  raised on the first step of every mission ever flown. The record showed a run
  that flew for five minutes, recorded nothing, and scored nothing — which
  reads as a controller that did not fly. A signature is a contract, and there
  is now a test that compares the two.

  **A mission got five minutes.** The duration a dive is given fell through to
  the default for a task with no stated limit, so a three-stage round asking
  for thirteen minutes was cut off part way through its first stage. A mission
  is the sum of its stages now, and may still be cut short on purpose.

  **A partial survey ended the round.** A stage that fails stops a mission —
  right for a dock that missed, because the next stage assumes a vehicle
  somewhere it is not. Wrong for a survey: a lawnmower pattern over a rectangle
  never reaches the hundred per cent that "done and not complete" tests
  against, so *every* mission with a survey in it stopped at its first stage
  and the frames never got inspected. A task now says whether failing it should
  stop the plan.

  **A dive did not say what it was flown in.** `layoutVersionId` was written to
  the row and never read back, so a dive flown in an arrangement read back as
  one flown over bare ground. Two thirds of what makes two runs comparable, and
  the record did not say either of them.

The round as written still runs out of time on its inspect stage — four of
twelve sides on one flight, none on the other. That is the plan being tight
rather than the platform being wrong, and saying so before a ship sails is what
the thing is for.

## 12 · The Missions tab, and a dive composed from one

`screens/Missions.tsx`, and `Dive.tsx` stops building an objective from nothing.

The dive page currently assembles a conditions document and an objective inline
and throws both away. It should pick things that exist and let any of them be
made on the spot.

**Done:** a dive is three choices and a button.

*Done (15 September).* Missions is a tab, and it is the only new one: a layout
stays filed under its place, because an arrangement *of* somewhere means
nothing away from it, while a plan of work is the unit of work itself — the
thing somebody comes in to write and comes back to fly.

Writing one is three columns, like the editor and for the same reason: the
arrangement and the palette on the left, the plan in order in the middle, and
what the selected stage is over on the right. The things a stage can point at
come from the arrangement's own document, by name — `cell-a ·
restoration-cell`, `nursery-frame-854--1099 · nursery-frame`, `riser ·
mooring-line` — so nothing can be pointed at that is not in the water.

The composer now leads with **Flying**: what plan of work, or nothing planned.
Choose one and Where and For disappear, because the plan says both — and the
place it names appears in the hero with its own depth, its reef and today's
sea, so a dive whose destination was implicit is still a dive somebody can
check before pressing the button. What is left is the plan, the vehicle, the
water, who flies it and how it knows where it is.

One thing the screen found, which nothing else would have:

  **Pointing at a thing worked for some tasks and not others.** A reach fell
  back to the objective itself and found `over` there; an inspect asked only
  for `target` and found nothing. So a stage written the same way in the
  editor aimed at a nursery frame for one kind of work and at "ten metres
  ahead of wherever you started" for the next — quietly, with a score to
  match. `over` now resolves in the base, where every task reads it.

## 13 · A run says what computed it, and which scenario it is

`packages/contracts`, `internal/dive`, one migration, `sim-runtime`.

Both fields at once, in one migration and one contract change, because the run
record should be altered once. Provenance is needed now; the sweep's scenario
reference is needed in the next step; splitting them means touching the same
table twice for no reason.

A run gains the sim image digest and a **physics version** the runtime declares
— a plain integer, bumped by hand when behaviour changes. It does not need to be
clever. It needs to change when the answer would.

Today the physics changed six times in one day and every result from before
became incomparable with every result after, silently, because the record pins
the place, the vehicle and the conditions and nothing about the simulator.

**Done:** two runs from either side of a bump cannot be put in one table without
the platform saying so.

*Done (15 September).* A run now carries three things it did not: the image
digest that actually computed it, a physics version the runtime declares, and
the scenario it is an answer to. One migration, as planned.

The two provenance fields answer two different questions and are kept apart for
that reason. The digest says *exactly* what ran, which is what a reproduction
needs. The version says whether the answer would have been the same, which is
what a table needs — a runtime rebuilt on a new base image has a different
digest and the same physics, and refusing to compare those would make the
platform useless by being right too often.

The Dives page keeps runs apart by it. A trial is grouped by the dive, the
controller *and* what computed it, so a controller "improved" on Tuesday is no
longer compared against itself across a physics change with the simulator
taking the credit; and any table that spans two says so in the vehicle colour
above the numbers. Shown against one dive flown twice today, once before the
declaration existed and once after: *"These runs were not all computed by the
same simulator — runs that did not say and physics 1."*

Getting the number onto the record took four attempts and every one of them
found something:

  **The record loses the first lines of every dive.** `brief` has been said
  since the beginning and has never once been recorded. Isaac Sim writes
  several hundred lines on the way up, and both readers of the simulator's
  output asked for the last four hundred — a window that is right for somebody
  watching and wrong for the record. The drain now reads all of it.

  **There are two ways into a dive and only one of them is `main`.** Any dive
  with a task, and any dive somebody is watching, is started as a Kit
  application against `coral_city.kit` and never runs `dive.main` at all. A
  declaration made there was made on the path almost nothing takes. It is made
  in `prepare` now, which is where both ways in meet, and still before anything
  is opened — so a run that fails while loading a scene says what it would have
  been computed by, which is exactly the run somebody is trying to compare.

  **Said aloud is not the same as written down.** The physics is now written
  beside the brief as well as said, because the file is for the agent and the
  event is for a person: a file is there whatever a log driver is doing and
  however much the simulator said on the way up.

## 14 · A sweep is a thing the platform runs

`internal/dive`, `internal/exec`, and the analysis lifted out of
`tools/what-if` unchanged.

A sweep is a mission, a list of what nobody can promise, and a threshold. The
cross product is submitted as a batch — the scheduler already does batches — and
each run carries the scenario it belongs to, which step 13 added.

The analysis moves across as it is: ranked by what **changes** the outcome
rather than by what was present when things failed, and dimensions that made no
difference named once and not ranked. That distinction is the difference between
a report somebody acts on and a grid nobody reads, and it is already written.

**Done:** a sweep runs from the platform and its answer is the same one the
tool gives.

## 15 · What it will cost

`internal/dive`, and the sweep's report.

Every input is already in the record and nobody has asked it for anything. A
dive knows its energy to a hundredth of a watt-hour and the battery knows its
capacity and reserve, so dives-per-charge is arithmetic. A mission knows how
long it took, so cells-per-day is arithmetic. A sweep knows what fraction of
scenarios failed, and that is the fraction of days lost to weather.

This is what turns "survives 23 of 50" into a sentence somebody can take to
whoever signs.

**Done:** a mission states what it will cost before it is flown, and a sweep
states what the weather will cost on top.

## 16 · The Sweeps tab

`screens/Sweeps.tsx`. Define the doubts, watch it fly, read the answer — a
paragraph and a small table, because the grid was tried and nobody could read
it.

**Done:** somebody who has never opened a terminal lays out a site, builds a
mission, sweeps it, and is told what to do about Tuesday. **This is the target
at the top of this file, and at this point the plan has met it.**

## 17 · The tether

`sim-runtime/coral/hydrodynamics.py` and `world.py`.

Everything after this is depth rather than reach. The tether comes first because
it is the only thing in the plan that is already **wrong** rather than missing:
a hundred metres of it streaming in a current has more area than the vehicle and
is often the larger force, and every tethered dive in the record flew without
it.

It sits here rather than at the start because its surface end is a thing on the
layout, which did not exist until step 5.

**Done:** a vehicle with a hundred metres out flies measurably differently from
one with ten.

## 18 · Doubts about the world, not just the water

`world.py`, and the sweep's doubt list.

Lines bow with the current — a quasi-static catenary, no solver, because the
displacement is metres and the metres are the point. Then the doubt list gains
entries that are not numbers: *the mooring is thirty metres from where it was
laid*, *the array has a transponder down*, *there is a net where the chart says
clear water*.

This is the half of the rehearsal that parameters cannot express, and it is
what the whole of steps 5 to 9 was for.

**Done:** a sweep can ask what happens if the world is not as drawn.

## 19 · The sonar becomes a sensor

`sim-runtime`, `world.py`.

Declared in the BlueROV2's package since the beginning — a hundred and thirty
degrees, half a metre to ten — and returning nothing, because there has been
nothing in the world to return off. Now there is.

**Done:** a controller can avoid something it has not been told about.

---

# How this is kept honest

**Nothing is touched twice, and here is where that was at risk.** The run record
is altered once, in step 13, carrying provenance and the sweep's scenario
together. The navigation is declared once in step 3, before any tab is added or
removed. The asset CRUD is generalised in step 4, before three kinds are added
to it. Those three were the rework in the previous draft of this plan.

**Restructuring is always in front of the thing that needs it.** Step 4 because
step 5 adds a kind. Step 6 because step 7 puts things in the water. Step 10
because step 11 needs tasks that accept references. No step splits a file on
principle, and `Dive`'s remaining fifty-odd methods stay where they are until
something needs them moved.

**A restructuring step that changes behaviour has failed.** Steps 4, 6 and 10
are checked by existing tests passing untouched — 193 of them, covering physics,
tasks, navigation, energy, surfacing and the glider. A test that has to change
means it was a rewrite wearing a refactor's name.

**Every step ends in something that runs.** Not a passing test: something flown
and looked at. Step 8 exists only to be that, at the point where the most could
be silently wrong.

**The record is cleared when physics changes.** After step 13 the platform can
say whether that was necessary instead of guessing.

**Two devices.** Steps 14 and 16 end in sweeps, and a sweep of seventy-two
scenarios takes most of a day on this box. That is the pacing constraint on the
back half; the free lever is shorter missions, not more planning.

**What would show this plan is wrong:** somebody who dives saying step 2 still
looks wrong; a site that cannot be laid out in five minutes at step 7; a sweep
at step 16 whose answer nobody acts on. None of the three is discoverable from
here, and each is worth stopping for.
