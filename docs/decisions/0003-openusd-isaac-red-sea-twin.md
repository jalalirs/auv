# 0003 — OpenUSD and Isaac Sim for the Red Sea Digital Twin

- Status: accepted
- Date: 2026-08-27

## Context

The Stonefish Living Reef is useful for learning vehicle dynamics, ROS 2,
sonar, and remote simulation, but it is not an adequate foundation for a
site-level Red Sea digital twin. The intended system must combine real reef
geometry, geospatial coordinates, time-varying observations and forecasts,
ecological annotations, simulated AUVs, synthetic data, and scientific replay.

No single robotics simulator supplies all of those capabilities. Ocean and
atmospheric forecast models must remain scientifically independent from the 3D
robotics runtime.

## Decision

Use OpenUSD as the canonical 3D scene-composition format and Isaac Sim as the
primary robotics, rendering, sensor, ROS 2, and synthetic-data runtime for
Project 002.

Build the project as independent layers and services:

1. source observations and forecast products;
2. normalized scientific data with provenance and uncertainty;
3. georeferenced reef and infrastructure assets;
4. time-varying OpenUSD scene composition;
5. Isaac Sim extensions for ocean state, underwater perception, and robotics;
6. ROS 2 autonomy and evaluation; and
7. an operational monitoring interface.

Oceanographic solvers are not reimplemented inside Isaac Sim. Their outputs are
sampled, replayed, visualized, and used as boundary conditions or disturbance
fields. Large source and derived assets remain outside Git and are addressed by
versioned manifests and checksums.

## Version strategy

Project assets and data contracts must not depend on a single Isaac Sim release.
The supported Isaac release is pinned per experiment. OceanSim and other
underwater research extensions are evaluated as references or adapters; they
are not allowed to dictate the project's canonical data model.

## Consequences

- The project gains a durable scene format, high-quality rendering, ROS 2,
  synthetic-data tooling, and a path to Isaac Lab.
- Underwater hydrodynamics, acoustic sensors, and optical effects require
  validation and likely custom extension work.
- Geospatial frames, timestamps, units, provenance, licensing, and uncertainty
  become first-class engineering requirements.
- The GPU host requires a separately approved operating-system, driver, and
  storage readiness plan before the current supported Isaac release is treated
  as production infrastructure.
- Stonefish remains a useful reference and teaching environment under Project
  001; it is not discarded.
