# Workflows

Finite work the platform runs as containers.

| Workflow | What it does |
| --- | --- |
| `ingest-bathymetry/` | Fetches a global relief grid and renders it for the map |
| `ingest-observations/` | Reads today's buoy observations and records them |

## What a workflow is

A container with declared inputs, declared outputs, and a stated size for each.
It runs with no capabilities, a read-only root, and exactly the processor and
memory the platform admitted it for. It holds no credential and reaches no route
on the platform: it writes files, and the platform reads them.

A workflow that publishes its result writes a **version descriptor** — a JSON
file stating the truth class, coordinate reference, vertical datum, extent, time
basis, uncertainty, rights, and attribution of what it produced. The platform
validates it exactly as it validates a version a person records
([ADR-0013](../docs/decisions/0013-a-job-may-publish-what-it-produced.md)). A
job gets no easier path.

## Reaching the outside world

These two do, which is unusual. Work runs with no network so that an
institution's container cannot reach anything; ingestion exists to bring the
outside world in, so it is granted egress explicitly and only a platform
administrator can submit it
([ADR-0012](../docs/decisions/0012-egress-is-a-capability.md)). Egress is all or
nothing, and that record says so rather than implying a control that does not
exist.

## Building them

```bash
./tools/build-workflows
```

Images are named by their content identity — `sha256:…` — rather than by a tag,
because a tag can be moved and the provenance of every version these produce
names the image that produced it. `tools/deploy-gpu` streams them to the GPU
host the same way it streams the platform's own images.

## What each records

**`ingest-bathymetry`** fetches a subset of NOAA NCEI's ETOPO 2022 global relief
model through NOAA's ERDDAP service, with the stride part of the request and so
part of the provenance. It keeps the grid exactly as it arrived and renders a
separate image for the map: two colour ramps, one for the sea floor and one for
the land, because a single ramp across both hides the coastline. The rendering
is a rendering; the grid beside it is what anyone measuring anything should
read. Its truth class is `analysis` — a compilation derived from measurements by
a documented method, not a measurement of its own.

**`ingest-observations`** reads the National Data Buoy Center's real-time feed
for a set of stations and takes each station's most recent complete report. Its
truth class is `observation`. A measurement a station did not report is named in
that station's `notReported` list rather than omitted, because an absent number
that is merely absent is indistinguishable from one nobody asked for.
