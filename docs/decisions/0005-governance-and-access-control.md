# ADR-0005: Governance and access control

- Status: Accepted
- Date: 2026-08-28

## Context

Cities may be open to everyone, restricted to a consortium, or invisible
outside one institution. Compute is scarce and must be governed as strictly as
data. A platform that grows several independent permission checks will
eventually disagree with itself, and retrofitting uniform authorization is
impractical once routes exist.

Some places must not be known to exist. Others should be discoverable but not
enterable, so that the catalogue is browsable and access can be requested.

## Options considered

1. Per-feature permission checks written where each route needs them.
2. Separate governance for data and for compute.
3. One access-decision point that every read and write passes through, covering
   every object including compute.

## Decision

Every object is governed by one decision point: layers, cities, orgs,
scenarios, vessels, stacks, experiments, runs, artifacts, jobs, sessions,
quota, and execution targets.

- **Scoped role bindings, not global roles.** A principal may be steward of one
  city, contributor to another, and unaware that a third exists. Bindings
  attach to a scope: platform, org, city, or object.
- **Discoverability and access are separate bits.**

  | State | Behaviour |
  | --- | --- |
  | `listed_open` | in the catalogue, enterable |
  | `listed_locked` | in the catalogue, 403 with a request-access affordance |
  | `unlisted` | 404 — indistinguishable from not existing |

- **Containment rule.** A layer's effective visibility is the intersection of
  its own policy and its city's. The API refuses to express a public layer
  inside a restricted city.
- **Grants, never copies.** Sharing is a grant edge. Duplicating bytes forks
  provenance and is prohibited.
- **Compute is governed identically.** The broker holds no policy logic of its
  own. Whether a principal may run a given stack, in a given city, on a given
  target, against a given quota, resolves through the same call as a read.
- **Denials are records.** Why access was denied and why a job was refused are
  first-class questions with rows behind them, not log lines.
- The decision point is the only component holding a policy database handle. A
  route-table test fails the build if any handler decides access for itself.

## Consequences

- A hosted public hub, a private institutional installation, and a hybrid
  become the same binary with different policy data, not a fork.
- Uniform enforcement is testable as a structural property rather than
  inspected during review.
- Governance appears in the first release and cannot be deferred.
- Every new object type must declare its scope and policy before it is exposed.
