# The world document (draft, 2026-11-03)

How a world is written down, and how it ties to the assets it is built
from. Draft for the user and the auv session to agree before anything is
built. Direction: `worlds-2026-11.md`.

## Three kinds of file, three jobs

| | What | Who makes it | Changes |
|---|---|---|---|
| **Source** | What came in: a GeoTIFF, an XYZ, a GLB, a video, a GEBCO tile | the person, or a public service | never; kept for provenance and re-import |
| **Native** | The same thing in our own form: a heightfield in metres, a model as USD, a reef as splat plus colonies | the importer of its workshop, once per asset version | with a new asset version only |
| **World** | A small document: which natives, where, how, plus what was authored in the world itself | the editor | every save, as a new world version |

The **importer is the transformer**. It reads the foreign format once, does
the projection, datum and scale arithmetic once, checks it once, and writes
our native form. The world never reads a GeoTIFF or a GLB. The arithmetic
that went wrong before (the NOAA export stretched 9.3%, the Sentinel seabed
stretched 2.4x) lives in one place per format, with a test, and not in every
reader.

The **world references, it does not copy**. Like a USD stage over its
layers, a Petrel project over its data, a Photoshop file over linked smart
objects: a bathymetry stays one asset in the library, used by any number of
worlds, each pinning the version it used.

## Natives, by kind

| Kind | Native form | Today |
|---|---|---|
| bathymetry | heightfield tiles: float32 height (z up, 0 at the surface), float32 error, uint8 source; its own georeference; metres per cell | stored only as uploaded; the places job reads it at build time |
| public source (GEBCO, Sentinel-2 depth, ICESat-2, Allen Coral Atlas, NOAA) | the same heightfield or cover grid, cut to an area, with citation and licence | fetched at build time and not kept as assets |
| structure | `model.usdc`, metres, z up, base on z = 0, footprint and stats | as today |
| reef from video | NuRec splat pieces, colony instances, footprint | as today |
| coral cover | a grid of cover and habitat class with provenance | inside the place build |
| life | the place's species list with observation counts (tools/fauna); groups, numbers and where fish swim are derived from it and the coral | the package's `life.file` |

## The document

A world version is one JSON document (`world.json`) plus any files the world
itself authored (painted masks), stored with the version. On disk and for
sharing it is a `.iocean` folder or zip: `world.json`, `owned/`, and, only
when packed for offline use, `natives/`.

```json
{
  "iocean": "world/1",
  "name": "Al Fahal",
  "frame": {
    "units": "m",
    "axes": "x east, y north, z up; z = 0 is the sea surface",
    "extentM": [2000, 2000],
    "origin": "middle"
  },
  "georef": {
    "origin": {"lat": 22.2531, "lon": 38.9583},
    "north": "true",
    "horizontal": "WGS84",
    "vertical": "MSL",
    "setBy": "terrain/gebco"
  },
  "layers": [
    {"id": "water", "kind": "water",
     "params": {"waterType": "Jerlov IB", "visibilityM": 12, "temperatureC": 28, "salinityPsu": 40}},

    {"id": "terrain", "kind": "terrain", "resolutionM": 2,
     "stack": [
       {"asset": "ast_gebco_…", "version": 1, "role": "depth", "priority": 0},
       {"asset": "ast_s2depth_…", "version": 3, "role": "depth", "priority": 5, "scale": 0.42},
       {"asset": "ast_icesat_…", "version": 1, "role": "check"},
       {"asset": "ast_survey_…", "version": 2, "role": "depth", "priority": 10}
     ],
     "result": {"asset": "ast_terrain_…", "version": 7}},

    {"id": "seabed", "kind": "seabed",
     "classes": {"0": "sand", "1": "rock", "2": "seagrass"},
     "paint": "owned/seabed.png"},

    {"id": "reef", "kind": "reef",
     "items": [
       {"id": "atlas", "asset": "ast_atlas_…", "version": 1, "role": "cover"},
       {"id": "video-reef", "asset": "recon_…", "version": 2,
        "at": [120.5, -40.2], "headingDeg": 15, "sits": "ground"}
     ]},

    {"id": "structures", "kind": "structures",
     "items": [
       {"id": "frame-1", "asset": "ast_nursery_frame", "version": 1,
        "at": [-1187.9, 759.3], "headingDeg": 30, "sits": "ground"},
       {"id": "ship-1", "asset": "ast_ship", "version": 1,
        "at": [-1113.5, -245.0], "sits": "surface"},
       {"id": "export-line", "asset": "ast_pipeline_…", "version": 1,
        "sits": "drape", "bendRadiusM": 150}
     ]},

    {"id": "life", "kind": "life",
     "from": {"asset": "ast_species_…", "version": 1}}
  ]
}
```

Rules:
- Every reference pins `asset` and `version`. Newer versions are offered,
  never taken silently.
- `sits` says how z is found: `ground` (rests on the terrain, worked out as
  the editor does today), `surface`, `drape` (along its own route over the
  terrain), `free` (z given).
- A layer has `visible` and `locked`; an item may too.
- An item with no place of its own (a model, a video reef with no
  navigation) takes its `at` in the world frame. One with a place (a survey,
  a route in degrees) is placed by the georeference and cannot be dragged
  off it.
- `georef` is null for a virtual world. The first georeferenced layer sets
  it; once one is in, it cannot change.
- `terrain.result` is the fused heightfield, a derived asset cached from the
  stack. Change the stack and it is made again; it is never edited by hand.

## Missions

A mission is its own versioned record, owned by one world (it cannot move
to another), saved against a world version. A dive pins the world version
and the mission version. The world document does not embed missions: they
change on their own and dives pin them on their own. The editor shows them
as a layer.

Stages refer to world items by id (`inspect frame-1`, `follow
export-line`). A mission saved against an older world version shows which
of its stages refer to items that moved or went.

## What a dive runs

A dive takes two things today, and keeps taking them (auv, 2026-11-03):

- **The package** (`cityPath`): `site.json`, the heightfield, the scene,
  `layers.coral` (coral.usda) with `reef.prototypeKinds` and
  `reef.swaysWith`, `layers.reconstructions` `[{name, file}]` for laid-in
  models and video reefs, `life.file`. A **bake** job makes it from a
  world version and caches it by that version. Same frame as the world.
- **The brief**: `layout = {version, things: [...]}` (the structures layer,
  written as things) with `layoutChanges` for rehearsals as today, and
  `conditions` for the water.

So the runtime does not change for the first worlds. Reading `world.json`
directly is later, if ever wanted.

### Structures as things

Each item becomes `{id, kind, ...}` with the item's own id, stable across
world versions, because mission stages point at it. Known kinds:
transponder, mooring-block, nursery-frame, marker-post, buoy, ship,
mooring-line, restoration-cell, pipeline, dredger; an unknown kind lands on
the ground.

| `sits` | Thing fields |
|---|---|
| `ground` | x, y; `groundM` or no z (the runtime lands it); radiusM, heightM |
| `surface` | x, y (a surface kind) |
| `free` | x, y, z |
| `drape` | laid: route `[{x, y}]`, bendRadiusM, stepM, exposed `[{fromM, toM}]`, features, shownBy |
| span (mooring line) | ends `[{x, y, z or groundM}] x 2`, slack, radiusM, weightNPerM |
| region (restoration cell) | corners `[{x, y}]` |

The brief's depths are positive down (depthM, groundM); the bake converts
from the world's z up. A USD model is drawn from `layers.reconstructions`,
not from things; when a mission must see, strike or inspect it, the bake
also writes a thing for it with `shownBy` naming the model, so it is not
drawn twice.

### Water

The world's water layer carries only what belongs to the place:
`waterType` (Jerlov), `visibilityM`, `temperatureC`, `salinityPsu`. Current,
wind and waves stay per-dive conditions as today (the runtime takes speed
and heading: `currentMetresPerSecond`, `currentHeadingDeg`, and so on). The
dive form starts from the world's water and the dive's conditions say the
rest.

### Life

One species-list asset for the first worlds. Authored schools with a region
and a count need a runtime change; on auv's list only if asked.

### Export

USD export for Maya and Unity: later. The scene is already USD, so it is
cheap when somebody asks.

## What today's records become

| Today | Becomes |
|---|---|
| a place (`catalog.city`) | a world |
| a place version (a package) | a bake of a world version |
| a place's `recipe.json` sources | the terrain stack, each source an asset |
| layouts (arrangements) | the structures layer of the one world; the many go away |
| assets: reef, structure, bathymetry | library assets with natives (bathymetry gains one) |
| missions (`catalog.layout`, kind mission) | missions owned by a world |

## Local and remote

The world document and its owned files live in the platform, versioned like
layouts are now. The app keeps a local cache of the natives a world uses,
so opening it again is instant and editing works offline; a save sends the
document. Renders from a viewpoint and bakes run on the box.

## Agreed with the auv session (2026-11-03)

Baking into today's package with the runtime unchanged; structures go in
the brief as things; water as above; life as a species list; USD export
later. auv flies the first bake on r7 against today's package for the same
place, as a dry run.
