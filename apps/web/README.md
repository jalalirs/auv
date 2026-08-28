# Coral City web

The primary scientist and programme interface for reef exploration,
environmental state, simulation sessions, mission review, and operations.

The web application consumes stable control-plane APIs. It does not own the
scientific archive or execute model jobs directly.

## Development

From the repository root:

```bash
pnpm --filter @coral-city/web dev
```

The development server proxies `/api` and `/health` to
`CORAL_CITY_CONTROL_PLANE_URL`, which defaults to `http://127.0.0.1:8080`.

See [`DESIGN.md`](DESIGN.md) for the current product boundary.
