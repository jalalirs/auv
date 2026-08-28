# Control plane

The future control plane owns identity and authorization, site and twin state,
missions and scenarios, workflow state, job state, simulator sessions,
publication state, and provenance.

It begins as a Go modular monolith with explicit internal boundaries. API style,
persistence technology, and production deployment have not been selected.

## Current foundation

The service currently exposes only:

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/platform`

Run it from the repository root with `just run`. The default address is
`http://localhost:8080`; set `CORAL_CITY_HTTP_ADDRESS` to override it. See
[`DESIGN.md`](DESIGN.md) for the complete boundary and acceptance evidence.
