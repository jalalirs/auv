# Control plane

- **Outcome:** one governed record of the ocean, and one place where every
  question about who may do what is answered.
- **Location:** `services/control-plane`.
- **Owned contract:** [`packages/contracts/v1/openapi.yaml`](../../packages/contracts/v1/openapi.yaml).
- **May call:** PostgreSQL with PostGIS, and an S3-compatible object store.
- **Forbidden:** running scientific work. It admits work and records what
  happened; workers run it.
- **Deployment:** one stateless process, and a separate one-shot command that
  applies the schema.

## What it owns

| Area | What it decides |
| --- | --- |
| `identity` | Who is acting: people, institutions, and service principals |
| `policy` | **Everything about who may do what, for every object including compute** |
| `city` | Places: their extent, reference system, datum, and discoverability |
| `layer` | Every datum, its versions, its manifest, its lineage, its publication |
| `storage` | Stored bytes and the record of them, addressed by content |
| `exec` | Work: admission, placement, attempts, events, quota, refusals |
| `audit` | The append-only record of what was done |

## The shape of it

Transport holds no domain logic. `httpapi` reads requests, calls the component
that owns the work, and writes responses; it makes no access decisions of its
own, because it cannot — the router applies them before a handler runs.

Each component owns its tables and nothing else's. `policy` is the only one that
holds a handle to the binding tables, which is what makes "access is decided in
one place" a structural fact rather than a convention.

## Three properties worth stating

**Every route is governed.** A route is declared with the action it performs and
the resource it acts upon; the router authenticates and consults the decision
point before the handler runs. `TestEveryRouteIsGoverned` fails the build if a
route was declared without either, and `PublicRoutes` lists the four endpoints
that work before anyone is known. There is no path to a handler that skips this.

**The contract cannot drift.** `TestTheContractDescribesEveryRoute` compares the
published description against the route table actually served and fails if
either contains an operation the other does not.

**Immutability is enforced by the record.** Triggers refuse to rewrite a
published version, a version's manifest, its lineage, the audit log, the job
event stream, an admission, or a refusal. A future code path cannot quietly
bypass what the schema will not accept.

## Where visibility is decided and where it is applied

The decision point produces a filter describing which versions a subject may
see; repositories apply it unchanged, through one predicate written once in
`internal/layer`. Deciding in one place and applying in another is what lets a
listing and a read agree about what exists without either deciding for itself.

## Bootstrapping

Establishing the first administrator is the one act that cannot go through the
API, because until it happens there is nobody to authorise it. `cmd/migrate
bootstrap` does it with direct access to the record, and is idempotent.

## What it deliberately does not do

No reconstruction, no environmental modelling, no simulator, no missions, no
Kubernetes, Slurm, or HPC adapter, no workflow engine, and no institutional
single sign-on. See [`docs/plan/r1.md`](../../docs/plan/r1.md).
