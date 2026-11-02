# iOcean, one environment: the plan (2026-11-02)

Consolidates todo section 73, items 1 to 15. iOcean is simulation and
modelling software for ocean vehicles. Running a vehicle is the core; places,
objects, vehicles and controllers are what a run is made of; the Store is
where iOcean's own versions of them come from.

## The rule

No tab per concept. A thing's parts live on the thing: a controller's
builds are its versions, a sweep is a run under several conditions, a
store place is a copy in your library. Tabs only for views of the same
list, never for different kinds of thing.

## The side bar

| Entry | What it is | Absorbs |
|---|---|---|
| **Home** | Every run, and starting one | Fly, Dive, Runs (Dives, Sweeps, Compare), the queue |
| **Missions** | Plans of work, drawn on a place's chart | the "plan" half of Fly |
| **Places** | Your places; open one to design it | Places tabs, New place, Build on it |
| **Objects** | Everything put in the sea: corals, wrecks, platforms, pipelines, reefs from video, models | Assets, Reconstructions |
| **Vehicles** | Your fleet, one grid | Fleet, Flyable/Catalogued tabs |
| **Controllers** | One list; each has versions, runs, scores | Controllers and Builds tabs |
| **Store** | What iOcean offers: places, objects, vehicles. Import copies into yours | Map store, catalogue |

## Progress

- 2026-11-02: steps 1, 2 and 4 built in the client, checked in the harness,
  not released. Runs is the home page; New run replaces Fly; Store, Objects
  and Vehicles are their own entries; Controllers has versions and a
  deploys strip instead of a Builds tab. Step 3 (the one run page) is next.
- 2026-11-02: step 3 built, not released. Every run opens the same page
  (screens/Run.tsx): title, back to Runs, a strip of facts. One condition:
  the replay under it. Several: what decides it in one line, a table of every
  condition with a score scale and the done mark, each setting's success and
  energy, and the cost as numbers. Any run opens now, recorded or not.
  Steps 1 to 4 are ready to ship as 0.2.0.

## Steps, in order

1. **Shell.** Side bar as above, Home first and the app opens on it. Rule
   written into docs/ui.md (the old "own tab" rule goes). Pages without a
   new home yet keep working under their new entry.
2. **Home: runs and flying in one.** One runs table for dives and sweeps
   alike: a run has a mission, a vehicle, a controller, conditions (one or
   several), a result. A sweep is a run row with "6 conditions" that opens
   to its results. Short result column (score, plain), no run-on lines.
   **New run** is the page's one primary action and opens a panel: mission,
   vehicle, controller, conditions as compact chip rows (one chip is a
   decision, several are a doubt), watch live. The Fly page goes.
3. **One run page.** The same page for any run: a single-condition run
   shows its replay and numbers; a multi-condition run shows a result grid
   (condition by outcome, with a scale), the deciding condition in one line,
   and the cost as a small table of numbers. Five type sizes only.
4. **Controllers.** One list; a controller's page carries its versions
   (builds, failures included), its runs and its scores. "Flown by" lists
   each controller once (newest version), the three built-in planners
   apart, and which fit the vehicle.
5. **Vehicles and Store, first cut.** Fleet becomes Vehicles, your vehicles
   only. A Store page with places and vehicles from iOcean, filtered by
   kind (one grid, not tabs). Using a store place says so while it works
   (item 1).
6. **Objects.** One page for every object you have, with real pictures,
   short names (source and licence on the object's page), search and a kind
   filter. New object has one short form per way in: a 3D model file, a
   dive video, a line drawn on a chart (pipeline, cable). Test leftovers
   archived.
7. **Import as a copy (platform).** Store items are copied into your
   organisation, any number of times; the original never changes. Needs
   control-plane work: today a store place is a binding, not a copy.
8. **The place designer.** New place starts from a terrain: one from the
   Store, your own survey, or a designed one. The editor: terrain canvas in
   the middle with level of detail from region to seabed; a palette of your
   objects; the selected object's properties beside it; ground, surveys and
   reefs as layers. Objects are placed, dragged, rotated.
9. **Live resolver.** Fitting objects to the terrain runs as you place
   them, not as a build step afterwards.
10. **Physics in the designer.** Dropped objects sink through the water and
    settle where the terrain catches them, on the coupled engine.

Small items ride along: the back crumb (item 2) is redrawn in step 1; the New
asset dialog (item 4) is replaced in step 6.

## Releases

Steps 1 to 4 are client only and ship together as 0.2.0. Steps 5 and 6 as
0.2.x. Steps 7 to 10 need platform and engine work and are planned with
you when 6 is out.

## Checking

Every step: the harness at 1280 x 800, at 100% and 125%, five type sizes,
one primary action, Back from anything opened. A screenshot of each changed
page in the report.
