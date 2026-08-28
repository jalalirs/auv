# Data services

Services will ingest observations and model products, normalize metadata, and
serve time-bounded site state. They remain independent from Isaac Sim so the
same data can support analysis, dashboards, validation, and alternate clients.

The foundation stage will define contracts before selecting production
infrastructure. Secrets and provider tokens remain outside Git.

## Implemented

- `catalog/`: validates survey manifests, exposes scientific-readiness blockers,
  and builds the deterministic source catalog used by every downstream service.
