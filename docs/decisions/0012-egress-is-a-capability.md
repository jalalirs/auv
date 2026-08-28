# ADR-0012: Egress is a capability

- Status: Accepted
- Date: 2026-08-28

## Context

Work runs with no network. That is deliberate: an organisation's container is
untrusted, and a job that cannot reach anything cannot exfiltrate what it was
given or fetch what nobody reviewed.

Ingestion breaks that. The daily loop exists to bring the outside world in —
bathymetry from a national archive, observations from a buoy network — and a
container with no network cannot fetch anything.

The two requirements are both right. What is wrong is treating them as one
setting.

## Options considered

1. Give every job network, and rely on review to catch misuse.
2. Fetch outside the job: a component with network downloads, and the job only
   transforms what it is handed.
3. Make egress a capability a job declares and the platform grants, held by the
   platform's own ingestion recipes and never by an organisation's work.

Option 2 is attractive and half-adopted already: a job's declared inputs are
fetched by the worker and staged read-only, so a job that reads a *pinned*
external file needs no network of its own. It fails for the daily loop, because
what a forecast or an observation feed returns today is not known in advance and
so cannot be pinned.

## Decision

**Egress is a property of a job, declared when it is submitted and refused
unless the submitter holds platform authority.**

- `none` is the default and applies to every job an organisation submits. The
  container gets no network, exactly as before.
- `internet` gives the container ordinary outbound networking. Submitting a job
  with it requires `job.submit_privileged`, which is bound at the platform.

**Egress is all or nothing, and this record says so rather than implying
otherwise.** A per-host allowlist would be the better answer and is not
implemented: enforcing one needs an egress proxy the containers are forced
through, which is its own decision. Recording an allowlist that nothing checks
would be worse than recording none, because it would read as a control.

The audit record and the job both carry which egress a job was granted, so
"which work could reach the internet" is answerable from data.

## Consequences

- The sandbox is unchanged for every job anyone but a platform administrator
  submits.
- Ingestion recipes are platform-owned by construction: an organisation cannot
  submit one, because it cannot grant itself the capability its image needs.
- A compromised platform administrator can run a container with network. That is
  true of a platform administrator generally, and is why the binding is separate
  and recorded.
- Narrowing egress to named hosts requires a proxy and a further decision.
