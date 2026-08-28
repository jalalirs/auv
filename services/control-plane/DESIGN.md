# Control-plane foundation design

- **Outcome:** provide the first observable Coral City runtime and a stable
  boundary for the web application.
- **Location:** `services/control-plane`.
- **Owned contract:** liveness, readiness, and public platform/build identity.
- **May call:** standard operating-system and HTTP facilities only.
- **Forbidden direct callers:** scientific solvers, robots, and simulator
  processes use future adapters rather than depending on this foundation.
- **Technology:** Go standard library. A third-party router or service framework
  adds no value for three read-only endpoints.
- **Data changed:** none. This service has no persistence.
- **Deployment:** one stateless process listening on a configurable address.
- **Evidence:** configuration unit tests and HTTP contract tests.
- **Replacement:** endpoints are isolated behind one handler; internal server
  organization can change without changing the HTTP contract.

## HTTP contract

| Method and path | Meaning |
| --- | --- |
| `GET /health/live` | The process can serve HTTP |
| `GET /health/ready` | Configured internal prerequisites are ready |
| `GET /api/v1/platform` | Stable product and build identity |

All responses are JSON and include `X-Request-ID`. Unknown routes and unsupported
methods use the Go HTTP server's standard status behavior. This checkpoint has
no authentication because it exposes no private or mutable state.
