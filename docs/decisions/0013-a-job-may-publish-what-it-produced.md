# ADR-0013: A job may publish what it produced

- Status: Accepted
- Date: 2026-08-28

## Context

Work produces receipted objects. Turning those objects into a layer version —
the thing that carries a truth class, a coordinate reference, a vertical datum,
a time basis, an uncertainty, and a place in the lineage graph — is done by a
person.

That is correct for a contribution somebody is standing behind. It is fatal for
the daily loop, whose whole point is that nobody triggers it. An ingestion that
required a person to publish its result would not be a heartbeat; it would be a
queue of chores.

## Options considered

1. The job calls the API and publishes its own result.
2. A separate process watches for finished ingestions and publishes them.
3. The job declares, when it is submitted, that one of its outputs becomes a
   layer version, and the platform materialises it when the job succeeds.

Option 1 means giving a container credentials and a route to the control plane.
A container that can publish can publish anything it can name, and the sandbox
exists precisely so that a job cannot act on the platform. It was rejected on
that ground alone.

## Decision

**A job may declare a publication: which layer its result belongs to, and which
of its declared outputs is the version descriptor.**

The descriptor is JSON the job writes, conforming to a schema in the contract,
stating everything a version must state. It is a declared, size-capped output
like any other, verified by digest like any other.

When the job succeeds, the control plane reads the descriptor, validates it, and
creates the version in one transaction:

- the producer is the job, and the version carries the recipe and the image
  digest that produced it;
- lineage is drawn from the job's input versions, so truth class propagates and
  a scenario input still makes a scenario output;
- the payload is the job's other declared outputs, whose digests the platform
  already verified when they were uploaded;
- publication and promotion happen only if the declaration asked for them, and
  promotion to the shared record still requires the submitter to hold steward
  authority in the scope.

The job holds no credential and reaches no route. It writes a file.

## Consequences

- The daily loop can be a heartbeat: an ingestion produces canonical evidence
  with complete provenance and nobody touches it.
- The control plane reads job output, which it did not before. That output is
  declared, size-capped, digest-verified, and schema-validated, and it is read
  only for jobs whose submitter asked for a publication.
- A job cannot publish anything it was not submitted to publish, because the
  layer and the intent are fixed at submission and the job cannot change them.
- Reconstruction (R2) and model runs (R3) use the same mechanism. Nothing about
  it is specific to ingestion.
