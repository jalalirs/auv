# ADR-0009: API style and contracts

- Status: Accepted
- Date: 2026-08-28

## Context

The platform's API will be consumed by a browser application, a field
application, workers, edge stations, ROS 2 components in C++, scientific
workflows in Python, and eventually partner institutions. Hand-written clients
in several languages drift from the server and from each other.

ADR-0001 places contracts above implementations in the dependency direction:
contracts must not depend on applications, runtimes, or solvers.

## Options considered

1. A hand-written JSON API documented separately from its implementation.
2. gRPC with protocol buffers as the primary external interface.
3. Contracts-first OpenAPI 3.1 with JSON Schema, generating clients.

## Decision

- `packages/contracts` holds versioned OpenAPI 3.1 and JSON Schema documents
  with stable `$id` URLs. It is the source of truth and depends on nothing.
- Schemas set `additionalProperties: false`. Unknown fields are rejected rather
  than ignored.
- Clients are generated from contracts. The web application uses a generated
  TypeScript client; hand-written request code is prohibited.
- Versioning is explicit in the path (`/api/v1/...`). Breaking changes require a
  new version, not a mutation of an existing one.
- Durable event streams are delivered over a streaming HTTP transport. A
  message broker is not introduced until measurement justifies one.
- gRPC may later be adopted for internal service-to-service traffic under its
  own decision record. It is not the external contract.

## Consequences

- Contract drift becomes a build failure rather than a support issue.
- Adding a consumer language means generating a client, not writing one.
- Contract changes are reviewable as diffs in a single place.
- Generation must run in continuous integration, and generated output must be
  identifiable and reproducible.
