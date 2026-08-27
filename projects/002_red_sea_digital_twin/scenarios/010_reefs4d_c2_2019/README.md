# Reefs4D C2 2019 inspection

This scenario is the first real reef in the Red Sea Digital Twin. The central
outcrop is a measured, textured photogrammetric reconstruction from Princess
Beach, Eilat, captured before the March 2020 storm. It remains at the authors'
meter scale and original Z coordinates.

The surrounding sand, water, rocks, and lighting are synthetic presentation
context. They are deliberately isolated below `SyntheticContext` and must not
be interpreted as observations.

The source PLY and generated visual USD stay outside Git under
`${AUV_DATA_DIR}/red-sea-twin`. Their committed manifests and deterministic
preparation code provide provenance and reconstruction instructions.

## Cameras

- `Overview`: default oblique site view
- `CloseInspection`: near-field morphology inspection
- `TopSurvey`: plan view for checking footprint and scale
