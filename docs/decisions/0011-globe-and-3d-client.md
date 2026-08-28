# ADR-0011: Globe and in-city 3D client

- Status: Accepted
- Date: 2026-08-28

## Context

The interface must eventually present a globe carrying real bathymetry and
current ocean state, a browsable catalogue of places, and a continuous
transition into a place where survey-grade geometry is explored at real scale.
Level-of-detail streaming is required in both regimes, and geospatial
correctness — projection, terrain height, vertical datum — must hold at every
zoom.

At the time of this record, none of that geometry exists. No bathymetry layer,
no terrain, and no reconstructed mesh has been ingested. Adopting a geospatial
3D engine now would produce a photorealistic empty globe: the most convincing
possible presentation of nothing, in a platform whose first rule is that
appearance must never imply certainty.

## Options considered

1. Adopt a geospatial 3D engine now and render an empty globe until data exists.
2. Adopt a general 3D engine and write the geospatial handling ourselves.
3. Draw only what the platform actually holds, and adopt the engine when there
   is geometry for it to render.

## Decision

**Until there is geometry, the interface draws only what the platform holds.**
Places are shown as their stated extents on a graticule, with their coordinate
reference, vertical datum, and bounds given as numbers. The map says plainly
that no bathymetry, terrain, or coastline layer is connected, because none is.
A survey-scale extent is drawn at a size a person can aim at rather than at
true scale, and the true extent is reported as a number beside it, so the mark
is a control and never a measurement.

**When the first terrain or mesh layer is published, CesiumJS is adopted** for
both the globe and the interior of a place. It provides an ellipsoidal globe,
terrain, projections, and 3D Tiles streaming, so the transition from globe to
place is one continuous camera movement rather than a handoff between engines —
and a hard cut at exactly the moment the product should feel continuous is the
failure worth avoiding.

**3D Tiles is the delivery format** for streamed geometry: bathymetry terrain,
survey meshes, point clouds, and structures. Tiling is a job output (ADR-0010),
produced once and stored as derived objects (ADR-0008). Source scientific
formats are never delivered to a browser; the browser receives tiles and the
archive keeps the originals.

**three.js is reserved** for views that are not geospatial at all, such as
vessel and sensor diagrams, where a globe is meaningless.

Every rendered view displays scale, north, coordinate reference, vertical datum,
and truth class, in whichever regime it is drawn.

## Consequences

- The interface never shows a surface the platform cannot account for.
- Adopting the engine is a self-contained change behind an existing screen,
  because what it replaces draws from the same layer list.
- A tiling stage becomes required in every geometry-producing pipeline.
- The client's capability will be bounded by what 3D Tiles can express; formats
  outside it need a conversion job.
- Replacing the engine later would mean replacing the delivery format, so this
  decision is load-bearing from the moment it is acted on rather than from now.
