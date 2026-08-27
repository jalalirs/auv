# Platform calibration scene

This is the smallest project-owned OpenUSD stage. It exists to prove that the
runtime preserves meters, Z-up orientation, the local ENU frame, transparency,
lighting, cameras, and ordinary USD geometry before any simulator extension or
large reef asset is introduced.

It is deliberately a calibration target, not a reef demo and not a scientific
site model. The first real reef enters through Project 002 milestone M1.

## Contents

- `stage.usda`: dependency-free OpenUSD stage
- `scenario.yaml`: identity, frame, runtime, and acceptance manifest
- `checksums.sha256`: stage integrity record
- `validate.sh`: local structural and compliance checks

## Validate

From this directory:

```bash
./validate.sh
```

The scene is accepted locally when it loads through `usdcat` and passes strict
`usdchecker` validation. M0 is not complete until this exact stage is also
opened under the pinned Isaac runtime and streamed to macOS.
