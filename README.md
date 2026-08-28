# Coral City

Coral City is a hub for oceanic engineering and science. This repository is its
monorepo.

It holds one shared, governed record of the ocean; lets people enter specific
places at survey fidelity; merges live daily observation with simulation; and
lets any organisation run its own jobs, scenarios, and autonomy software against
that world under reproducible conditions.

The domain is not limited to coral. Reefs, offshore platforms, ports, wind
farms, fishing grounds, and coastal structures are the same objects with
different content. The platform is not specific to any one sea.

## The model

Five nouns and one edge. Everything else is a detail of these.

```
platform
├── layer/{id}@{version}   global: bathymetry · ocean forecast · weather · imagery
│
├── city/{id}              a bounded, curated, navigable place
│   └── layer/{id}@{v}     survey-grade: mesh · orthomosaic · structures ·
│                          local fields · observations · simulation output
│
└── org/{id}               an institution: members, quota, and its own work

grant:  org | principal ──[role, discoverability]──> city
```

A city and an organisation are **siblings** under the platform. An organisation
never contains a city; it holds a grant to one. Cities outlive the institutions
that funded them, because the record of a place must not be a child of whoever
paid for the dive.

## Three rules

**Access is decided in one place.** Every read and every write — including every
request to run work — resolves through a single decision point
([ADR-0005](docs/decisions/0005-governance-and-access-control.md)). A test
refuses any build in which a route was declared without one. There are two ways
of being refused: a hidden refusal reports absence, because the existence of
some places is itself sensitive, and a visible one says the object exists and
access may be requested. Both are recorded, so "why can I not see this" is
answerable from data.

**Evidence is never rewritten.** A published version is immutable, enforced by
the database and not by convention. Corrections create new versions that
supersede the old; retraction withdraws a version without deleting it or its
lineage. Every version states its coordinate reference, vertical datum, time
basis, rights, and uncertainty — of which "unknown" is an answer and absence is
not.

**A truth class does not strengthen.** Anything derived from a scenario is a
scenario, permanently. The database refuses to record otherwise.

## Repository map

| Area | Responsibility |
| --- | --- |
| `apps/web` | The scientific web application |
| `services/control-plane` | Identity, governance, places, layers, provenance, work |
| `services/worker` | Leases work and runs it as a container |
| `packages/contracts` | The versioned API description; the source of truth |
| `packages/client-ts` | The client generated from it |
| `deployments/` | The local and GPU deployments |
| `docs/` | Vision, architecture, plan, and reviewed decisions |
| `tools/` | Human entry points for repository operations |

A directory appears here only when it holds something. There is no `projects/`
layer: Coral City is the project.

## Running it

```bash
mise trust && mise install
just setup
just run
```

That builds and starts the whole platform — PostgreSQL with PostGIS, an
S3-compatible object store, the control plane, a worker, and the web
application — applies the schema, establishes the first administrator, and
provisions the worker. It prints where to sign in.

```bash
just check    # formatting, vetting, types, and contract currency
just test     # every component's tests
just e2e      # the whole platform, end to end, including worker crash recovery
just logs     # what it is doing
just reset    # stop it and discard everything it holds
```

## Boundaries

- Git stores code, contracts, migrations, recipes, manifests, and small
  fixtures. It does not store surveys, video, meshes, point clouds, NetCDF,
  Zarr, ROS bags, model output, or renders.
- Observations are immutable. Corrections create versions.
- Every derived artifact identifies its source, recipe, software version,
  checksums, coordinates, time basis, truth class, and uncertainty.
- Work supplied by an organisation is untrusted: no network, no capabilities, no
  way to gain privileges, a read-only root, and the resources it was admitted
  for.
- Scientific solvers run behind adapters and never define Coral City APIs.
- Vehicle safety and low-latency control will remain local to the field edge.

## Where this is

The platform spine is built and running: identity, institutions, governance,
places, layers, immutable versions, provenance, content-addressed storage, the
job model, a real worker, quotas, refusals, and an append-only audit record.
[`docs/plan/r1.md`](docs/plan/r1.md) says what is deliberately not built yet —
most of it, including all reconstruction, all environmental modelling, and the
simulator.

Start with [the plan](docs/plan/r1.md), the
[decisions](docs/decisions/README.md), and the
[architecture](docs/architecture.md).

## Synchronization

```bash
just sync "describe the approved change"
./tools/deploy-gpu
```

The previous repository is recoverable from Git tag
`legacy-before-restart-2026-08-28`.
