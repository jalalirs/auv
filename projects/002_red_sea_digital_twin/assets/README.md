# Asset boundary

This directory contains small manifests, schemas, and composition files—not raw
photogrammetry, textures, point clouds, bathymetry, or generated USD packages.

Large assets live under `/data/red-sea-twin/assets` on the execution target.
Every asset is addressed by a versioned manifest containing its provenance,
license, checksum, coordinate metadata, and deterministic preparation steps.

Planned representations for a reef site are:

- immutable source capture or download;
- analysis geometry at scientific resolution;
- optimized visual geometry with levels of detail;
- simplified collision geometry; and
- semantic annotations linked to, but not destructively baked into, geometry.
