# Asset boundary

This directory contains small manifests, schemas, and composition files—not raw
photogrammetry, textures, point clouds, bathymetry, or generated USD packages.

Large assets live below `${AUV_DATA_DIR}/red-sea-twin/assets` on the execution
target. The GPU-host default is
`/home/jalalirs/code/auv-data/red-sea-twin/assets`; containers mount this as
`/data/assets`. Every asset is addressed by a versioned manifest containing its
provenance, license, checksum, coordinate metadata, and deterministic
preparation steps.

Planned representations for a reef site are:

- immutable source capture or download;
- analysis geometry at scientific resolution;
- optimized visual geometry with levels of detail;
- simplified collision geometry; and
- semantic annotations linked to, but not destructively baked into, geometry.
