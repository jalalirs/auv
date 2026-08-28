# ADR-0004: World object model

- Status: Accepted
- Date: 2026-08-28

## Context

Coral City is a hub for oceanic engineering and science. It holds one shared
record of the ocean, lets people enter specific places at survey fidelity,
merges live observation with simulation, and lets organisations run their own
jobs, scenarios, and autonomy software against that world.

Two models were considered and one was rejected during design review. Treating
scientific places as assets owned by the organisation that surveyed them makes
the record of a place a child of whoever funded the dive. It also makes
consortium work a special case and forces object identity to change whenever
access changes.

The domain must not privilege coral. Reefs, offshore platforms, ports, wind
farms, fishing grounds, and coastal structures must be the same objects with
different content.

## Options considered

1. Organisation-owned sites, with a separate public catalogue for shared data.
2. A single public world with no private content.
3. One structure for everything, with access expressed as governance rather
   than as containment.

## Decision

Adopt one object structure. City and organisation are siblings under the
platform; neither contains the other.

```
platform
├── layer/{id}@{version}   global scope: bathymetry, ocean forecast, weather,
│                          imagery, coastline
├── city/{id}              a bounded, curated, high-fidelity, navigable place;
│   └── layer/{id}@{v}     city scope: mesh, point cloud, orthomosaic,
│                          structures, local fields, observation series,
│                          annotations, simulation output, telemetry
└── org/{id}               an institution: members, quota, and its own work —
                           scenarios, vessels, stacks, experiments, runs

grant: org | principal ──[role, discoverability]──> city
```

- A city exists at the platform and is addressed `platform/cities/{id}`
  permanently. An organisation holds a grant edge to a city, never the city.
- Containment and attribution are distinct. A contributed layer is contained by
  the city and attributed to the organisation. It is city-scoped from upload,
  restricted by policy until promoted.
- Cities inherit platform-scoped layers as background and as boundary
  conditions for local models.
- The world is not a city. Global layers are platform-scoped, because a coarse
  global field and a bounded survey-grade map behave differently in meshing,
  level-of-detail, and solving.
- A derived city may reference canonical layer versions and add its own. No
  bytes are copied.
- Every layer version carries a truth class: `observation`, `analysis`,
  `forecast`, `scenario`, or `simulation`. Truth class propagates down lineage
  and can never be upgraded by a derived job.

## Consequences

- Cities outlive the organisations that funded them, which is required of a
  scientific record.
- Consortium access is native rather than special-cased.
- Citations, layer references, and scenario pins survive every change of grant.
- Adding non-reef domains requires new layer types, not new architecture.
- Promotion of a contributed layer is a policy change, not a data move.
- The truth-class rule must be enforced by non-nullable columns and API
  validation, never by the interface.
