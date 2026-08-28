# ADR-0007: Persistence

- Status: Accepted
- Date: 2026-08-28

## Context

The platform must store institutional identity, governance policy, cities and
their extents, layer versions with spatial metadata, provenance lineage,
execution state, and an append-only audit record. Spatial queries over city
extents and layer footprints are central rather than incidental.

Scientific payloads — gridded fields, meshes, point clouds, imagery — are large
and must not be stored in a relational database.

## Options considered

1. A relational database plus a separate specialised spatial store.
2. A document database for flexibility during early domain evolution.
3. One PostgreSQL instance with PostGIS, schema-separated by domain.

## Decision

- One PostgreSQL instance with PostGIS is the system of record.
- Schemas separate domains: `identity`, `policy`, `audit`, `store`, `city`,
  `layer`, and `exec`. Schema separation is preparation for later physical
  separation, should it ever be justified by measurement.
- Migrations are numbered and named in plain English so that the schema is an
  auditable ledger of decisions. They are applied by an explicit command and
  never on service startup.
- Scalar observation series live in partitioned tables. **Gridded fields,
  meshes, point clouds, imagery, and tiles never enter the database.** They are
  objects in storage with a catalogue row and a spatial and temporal index
  (ADR-0008).
- Provenance lineage and audit events are append-only. Nothing published is
  updated in place; corrections create new versions.

## Consequences

- Spatial correctness is available from the first release rather than bolted on.
- Payload size in the database stays bounded by design.
- A schema change is a reviewable artifact with a readable name.
- Introducing a second storage engine requires another accepted ADR.
