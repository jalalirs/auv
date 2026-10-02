# r6: how the engine is built

How the coupled ocean is coded, in what language, how its parts talk to each
other, what it looks like when it is finished, and how it carries everything
built so far.

## Language

**Python, with the heavy parts in NVIDIA Warp.** Not C or C++.

- **Python** for the systems, the schedule and the glue. It is what the runtime,
  the controllers, the SDK, the MCP server and Isaac Sim already speak, and it
  is the language the user reads.
- **numpy** for anything small: one vehicle, a few dozen fish, a sonar's three
  beams. It is C underneath, and fast enough at that size.
- **Warp kernels** for anything that grows with the world:
  - the water field and the thruster jets
  - the sediment grid
  - the cable's segments
  - neighbour search across thousands of fish

  Warp is Python that compiles to CUDA. It ships inside Isaac Sim and also runs
  on the CPU, so the same kernel runs on the box's GPUs and in the tests on the
  Mac.
- **Newton** (NVIDIA's physics engine, built on Warp, Apache-2.0) for the
  cable's rod and for contact, if its version fits the Isaac Sim image on the
  box. That is checked first. If it does not fit, the cable is our own XPBD rod
  in Warp, which is about four hundred lines.
- **C++ only if a measurement says so.** A system that is over its time budget
  after it has been moved to Warp is the only reason to write any.

## Principles

1. **Computing is not drawing.**
   - A system computes state and never touches USD.
   - A separate drawing layer, which runs only inside Isaac, reads that state
     and writes the stage: fish instancer, propellers, cable curve, plume,
     coral.
   - An undrawn dive therefore runs the same physics as a drawn one, at 15
     times real time instead of 0.17.
   - This is already true of the vehicle (`step` and `show`). It becomes true
     of everything.
2. **One world, and each part of it has one owner.**
   - The world state is a set of named slices, for example `water`, `vehicle`,
     `fish`, `coral`, `cable`, `sediment`, `light` and `contacts`.
   - Exactly one system writes each slice, and any system may read it.
3. **Systems never call each other.** They meet only in the world state. The
   fish do not ask the vehicle where it is; they read `vehicle.pose`. The
   thrusters do not push the fish; they write jets into `water`, and the fish
   read the water. That is what makes the ocean coupled, and also what keeps
   each module readable on its own.
4. **Every system declares what it reads and what it writes,** and how often it
   runs. The engine works out the order from those declarations and prints it.
   - Where two systems feed each other (the vehicle stirs the water, the water
     drags the vehicle), one side reads the *previous* tick, and says so in its
     declaration.
   - That one-tick delay is honest physics at a 1/60 s step, and it is visible
     rather than hidden in a call order.
5. **One clock, fixed steps, and deterministic.**
   - Every system runs at a whole multiple of the base step: sonar at 10 Hz,
     fish at 20 Hz, the cable in sub-steps.
   - Every source of randomness is a generator seeded from the dive's seed and
     the system's name. The same seed gives the same dive to the millimetre.
     That is how a refactor is proven to change nothing.
6. **Numbers live in sheets, not in code.**
   - Species, coral kinds, thrusters, tethers and water types are data files.
   - Every value names its source and its kind: measured, derived, chosen or
     assumed.
   - The engine reports the kinds with the results, as the platform already
     does.
7. **Every system is tested against the world, not against itself.**
   - Each module's tests check its outputs against published numbers: kick
     intervals, jet decay, settling speed, cable tension in the DFKI tank data.
   - The whole is held to a regression: the iocean round trip, on its seed.
8. **Readable by someone who did not write it.**
   - One module per system, aiming for under five hundred lines.
   - The opening docstring says the model, the papers, what the system reads
     and writes, and what it assumes.
   - Plain names, no framework, no metaclass, no plugin registry. A system is a
     class with `reads`, `writes`, `every` and `step(world, dt)`.
   - Comments say why, in the house style that is already there.
9. **Moved, not rewritten.**
   - `runner.py` is 3,900 lines and works. Systems come out of it one at a
     time, each behind the regression, and the runner shrinks to the loop that
     steps them.
   - Nothing is deleted until its replacement has flown the same dive.
10. **Time is budgeted.** Each system has a millisecond budget per tick. The
    engine measures each one and reports it with the dive, as `life_costs`
    already does for the fish.

## How the parts interact

```
                light ───────────────┬────────────┬──────────────┐
                  │                  │            │              │
 conditions ──► water ◄── thrusters ◄── controller ◄── sensors ◄─┤
   (current,      │  (jets)      (commands)                      │
    wind, tide,   ├─────────► vehicle ◄── cable ◄──┐             │
    pump)         │             │  ▲               │             │
                  │             ▼  │               │             │
                  ├────────► contacts ─────────────┤             │
                  │             │                  │             │
                  ├──► fish ◄───┤  (looming: vehicle pose)       │
                  ├──► coral ◄──┘  (strikes, wash, smothering) ──┤
                  └──► sediment ──► (visibility, smothering) ────┘
                                         │
                                       judge ──► dive result (failed: tether held …)
```

| Slice | Written by | Read by |
|---|---|---|
| `water` (velocity anywhere, any time) | water: background current, tide, surge, wind, pump; thrusters: jets | vehicle, fish, coral, cable, sediment, snow |
| `vehicle` (pose, velocity, thruster RPM) | vehicle dynamics | everything; the drawing spins the propellers from RPM |
| `cable` (nodes, tension at each end, contacts, winding) | cable | vehicle (pull at the attach point), judge, drawing |
| `contacts` (who touched whom, where, impulse) | contact | vehicle, fish, coral, cable, record |
| `fish` (position, heading, intention, fear) | fish | sonar (echoes), camera (counts), drawing |
| `coral` (bend, broken, smothered, polyps out) | coral | contact (shape), drawing, record |
| `sediment` (concentration grid, deposits) | sediment | camera (visibility), turbidity sensor, coral |
| `light` (hour, sun or LEDs, attenuation by depth) | light | fish, coral, camera exposure, drawing |
| `readings` | each sensor | controller (through the SDK's topics, unchanged) |
| `verdict` | judge | dive result, MCP |

A tick, in the order the declarations give:

1. light
2. water's background, then the jets from last tick's commands
3. cable
4. contact
5. vehicle
6. fish
7. coral
8. sediment
9. sensors, each at its own rate
10. controller
11. judge
12. record

The drawing runs at its own frame rate, from whatever the world holds.

## What it looks like on disk

```
services/sim-runtime/coral/
  engine/        clock, world (the slices), system (the four-part shape), schedule (order from declarations, budgets)
  systems/       one file each: water, thrusters, vehicle, cable, contact, fish, coral, sediment, light, judge
  sensors/       sonar, multibeam, camera, navigation, ctd, turbidity, side-scan, sub-bottom (each a system)
  kernels/       the Warp kernels the systems call: jets, grid advection, cable, neighbours
  sheets/        species, coral kinds, thrusters, tethers, water types — data with provenance
  draw/          the only place that imports pxr: fish, propellers, cable, coral, plume, caustics
  controllers/   unchanged
  runner.py      the Dive: loads place, vehicle, mission; builds the world; steps the engine
```

## How it carries what we have built

- **Places:** `site.json`, the heightfield, the USD scene, the fixed views, the
  rig and the stocked life are what the world is built from. Nothing changes
  for a place already published. New fields, such as rocks as refuges and a
  wariness setting, are optional.
- **Vehicles:** `vehicle.json` from the catalogue already gives thrusters,
  sensors, tether and mass. Thrusters gain a propeller diameter, for the jets
  and the drawing; tethers gain bend radius and breaking load. Packages already
  published still load.
- **Controllers and the SDK:** untouched. A controller reads the same topics
  and commands the same thrusters. It simply flies in an ocean that answers
  back. `wary`, `pursue` and every controller already deployed keep working.
- **Missions, objectives, scoring:** unchanged, with one new way to fail (the
  tether held) and new sections in the result: disturbance, count bias and the
  tether's state.
- **MCP:** `dives_start` and `dives_result` keep their shape. The result gains
  those sections, with their provenance.
- **Provenance:** every new number arrives as `{value, kind, from}`, as every
  number already does.
- **Rendering:** the film mode, the materials, the textures and the fixed views
  stay. The drawing layer adds spinning propellers, the moving cable, broken
  and bending coral, and the plume.
- **Deploy:** the same image, rsync, build and push to the box. No new service.

## What is checked first, because it can change the plan

1. **The Isaac Sim image's Warp version, and whether Newton installs beside
   it.** That decides whether the cable and contact are Newton's or ours.
2. **Warp on the Mac's CPU, for the tests.**
3. **The regression itself:** the round trip recorded today, to the millimetre,
   before anything moves.

## As built, 2 October

What the first day made of the layout above, and where it differs.

**The schedule** (printed by `dive.engine.order()`, worked out from the
declarations, never written by hand):

```
 1. faults      2. ship        3. light       4. water       5. views
 6. navigation  7. ctd         8. quality     9. multibeam  10. sonar
11. helm       12. thrusters  13. vehicle    14. wash       15. cable
16. clock      17. fish       18. coral      19. sediment   20. sidescan
21. tasking    22. bridge     23. record
```

Everything before the clock senses and decides on the world as the tick found
it. The vehicle integrates. The wash and the cable follow the vehicle. Then the
clock moves on, and what follows judges the state the tick produced: the fish,
the coral, the sediment, the side-scan, the task and the record. Where a loop
had to be closed, one side reads the start of the tick, and says so. Examples:

- The sonar hears the fish where they were.
- The sonde reads the sediment as it was.
- The vehicle feels the cable's last pull.

A declaration that made a loop was refused with the loop named. That happened
once, to the sonde, and the fix was one word.

**Where it differs from the plan above:**

- **No `sensors/`.** The instruments are systems in `systems/instruments.py`
  (CTD, sonde, multibeam, sonar) and `systems/sidescan.py`.
- **No `kernels/` and no Warp yet.** Every system runs in numpy well inside its
  budget at these sizes: 30 fish or 1,272, a 60-node cable, a few thousand
  sediment parcels. The sonar's ray-march was the one hot spot, and
  vectorising it took it from 4.1 to 0.36 ms a tick. Warp is for the grid
  water and reef-sized sediment, when they come.
- **No `sheets/`.** The species are `coral/fish_species.py`. Thrusters, tethers
  and cameras are read from each vehicle's own package, which already was the
  sheet.
- **Contact is functions the vehicle calls** (`systems/contact.py`), not yet a
  system of its own. Every strike now has a place, a speed and an impulse.
- **`runner.py` keeps the old attribute names** as views onto the world
  (`_kept`). Everything outside the tick — the console, the drawing, the
  reports — still reads them. That is the next thing to thin.

**What holds it:** `tools/regress` flies three reference dives:

- the tank round trip in still water;
- the same round trip with the fan on;
- Luna's transect at Looe Key.

Every change either leaves all three identical to the last digit, or changes
them on purpose and re-records them, saying why in its commit.
