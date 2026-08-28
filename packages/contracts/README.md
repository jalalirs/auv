# Contracts

The versioned description of everything Coral City exposes.

This package is the source of truth for the shapes the platform accepts and
returns. It depends on nothing: not on the services that implement it, not on
the applications that consume it, and not on any runtime. Everything else
depends on it.

## What is here

| Path | Contents |
| --- | --- |
| `v1/openapi.yaml` | Every endpoint, its request, and its responses |

## Keeping it true

A description that drifts from the thing it describes is worse than none, so
drift is a build failure rather than a review note.
`TestTheContractDescribesEveryRoute`, in the control plane, compares this
document against the route table the router actually serves and fails if either
contains an operation the other does not.

## Generated clients

The web application's client is generated from this document. Hand-written
request code is not permitted (ADR-0009): a hand-written client drifts silently,
and a generated one cannot.

```bash
just contracts
```
