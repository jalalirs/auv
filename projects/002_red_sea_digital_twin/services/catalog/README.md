# Reef survey catalog

This service is the first operational slice of R1 Scientific Reef Atlas. A
single source manifest becomes a deterministic catalog record without manual
scene editing.

The contract validates identity, truth class, rights, immutable file checksums,
WGS84 anchor, vertical datum, physical scale, geometry bounds, and explicit
scientific limitations. A valid record can still be `blocked`: incomplete
scientific facts are visible and do not silently become trusted geometry.

```bash
./tools/reef-catalog validate
./tools/reef-catalog build
./tools/reef-catalog show reefs4d.c2.2019
./tools/reef-catalog test
```

The canonical JSON Schema is
`contracts/reef-survey-manifest.schema.json`. The command performs the same
domain checks plus cross-field checks that JSON Schema alone cannot express,
including extent/bounds consistency and publication-readiness blockers.
