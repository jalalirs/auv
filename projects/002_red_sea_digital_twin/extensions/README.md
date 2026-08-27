# Isaac Sim extensions

Project-owned extensions will use the `redsea` namespace and remain small,
composable adapters.

Expected extension boundaries:

- `redsea.site`: site loading, local frames, and metadata inspection;
- `redsea.ocean_state`: timestamped environmental-field sampling and display;
- `redsea.underwater_optics`: calibrated camera-medium effects;
- `redsea.sonar`: staged acoustic sensor models;
- `redsea.telemetry`: live/replay observation adapters; and
- `redsea.provenance`: visible run and asset identity.

OceanSim and other research extensions are evaluated behind adapters. Their
internal schemas do not become the canonical project schema.
