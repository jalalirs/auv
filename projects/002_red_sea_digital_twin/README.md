# Project 002 — Red Sea Digital Twin

## Vision

Build a living, scientifically traceable 3D twin of Red Sea reef and dive sites
that can answer three classes of question:

1. **What was, is, or may be happening at this site?**
2. **How is the reef geometry and ecological state changing?**
3. **How would an AUV observe, navigate, or sample the site under those
   conditions?**

The project is not a prettier simulator world. It is a long-lived integration
of measured geometry, environmental observations, forecasts, robotics, and
reproducible scientific scenarios.

## First vertical slice

The first end-to-end result will:

- import one openly available Red Sea reef reconstruction into OpenUSD;
- retain source, license, checksum, scale, coordinate-frame, and processing
  provenance;
- render the site remotely on the Mac through Isaac Sim;
- replay a small timestamped wind, wave, and temperature data set;
- show the difference between observed, forecast, and simulated values;
- place one controllable AUV in the site through ROS 2; and
- record a reproducible run with scene, data, software, and configuration IDs.

## Workstreams

| Workstream | Owns |
| --- | --- |
| Platform | GPU readiness, Isaac Sim, OpenUSD, streaming, CI |
| Reef data | Photogrammetry, bathymetry, coordinates, semantics, change |
| Ocean data | Observations, forecasts, normalization, replay, uncertainty |
| Simulation | Ocean-state visualization, forces, optics, acoustic sensors |
| Robotics | Vehicle assets, ROS 2, control, SLAM, missions, evaluation |
| Operations | Site catalog, monitoring, alerts, dashboards, provenance |
| Research | Literature, hypotheses, validation, publications, partnerships |

## Principles

- Observations are immutable; corrections create new versions.
- Every derived asset points to its source, license, processing recipe, and
  checksum.
- Geographic position, local frame, vertical datum, units, and time basis are
  explicit.
- A visualization is not treated as a forecast, and a simulation is not
  treated as an observation.
- Uncertainty is retained instead of hidden behind photorealism.
- Site geometry, ocean state, vehicles, and experiments are composable rather
  than baked into one monolithic scene.
- The smallest useful site is completed before attempting the whole Red Sea.

## Non-goals for the foundation stage

- Solving basin-scale atmosphere or ocean circulation inside Isaac Sim
- Claiming coral-health inference from wind or surface waves alone
- Building an entire Saudi reef before validating one small site
- Treating unvalidated sonar, optics, or hydrodynamics as sensor-grade truth
- Committing large meshes, imagery, NetCDF, Zarr, bags, or renders to Git

## Project documents

- [Architecture](architecture.md)
- [Roadmap and gates](roadmap.md)
- [Initial data sources](data-sources.md)
- [Platform and runtime](platform/README.md)
- [Asset boundary](assets/README.md)
- [Isaac extensions](extensions/README.md)
- [Data services](services/README.md)
- [Scenarios](scenarios/README.md)
