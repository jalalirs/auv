# Architecture decisions

This directory contains numbered Architecture Decision Records (ADRs).

Each record states the context, considered options, decision, consequences,
status, and date. A proposed record must be reviewed before code depends on it.
Superseded records remain in Git so the reasoning is never lost.

## Accepted

1. [ADR-0001: Language and runtime policy](0001-language-and-runtime-policy.md)
2. [ADR-0002: Monorepo tooling](0002-monorepo-tooling.md)
3. [ADR-0003: Product surfaces](0003-product-surfaces.md)

These records define the platform itself. They were reviewed together, because
each depends on the object model in ADR-0004.

4. [ADR-0004: World object model](0004-world-object-model.md) — platform-scoped
   layers, cities, organisations, and grants. Everything else follows from this.
5. [ADR-0005: Governance and access control](0005-governance-and-access-control.md) —
   one decision point over every object, including compute.
6. [ADR-0006: Identity and authentication](0006-identity-and-authentication.md) —
   people, organisations, service principals; no anonymous read.
7. [ADR-0007: Persistence](0007-persistence.md) — PostgreSQL with PostGIS as the
   system of record.
8. [ADR-0008: Object storage and immutability](0008-object-storage.md) —
   content-addressed S3-compatible storage; evidence is write-once.
9. [ADR-0009: API style and contracts](0009-api-style.md) — contracts-first
   OpenAPI and JSON Schema, generated clients.
10. [ADR-0010: Execution model](0010-execution-model.md) — jobs, attempts,
    events, pluggable targets, leased workers, untrusted containers.
11. [ADR-0011: Globe and in-city 3D client](0011-globe-and-3d-client.md) — draw
    only what the platform holds; adopt a geospatial engine when there is
    geometry to render.
12. [ADR-0012: Egress is a capability](0012-egress-is-a-capability.md) — the
    sandbox stays closed; reaching the internet is granted, not assumed.
13. [ADR-0013: A job may publish what it produced](0013-a-job-may-publish-what-it-produced.md) —
    how the daily loop becomes a heartbeat without giving a container credentials.

## Expected later

1. Environmental model adapter boundaries.
2. Compute resource brokering across Kubernetes, Slurm, and institutional HPC.
3. Isaac Sim and ROS 2 version policy.
4. Field-edge safety authority and offline synchronisation.
5. Data retention and lifecycle policy.
