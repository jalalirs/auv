# Roadmap

The roadmap is milestone-driven. A phase is complete only when its result can be
launched, observed, recorded, and reproduced.

This document tracks the marine-robotics learning sequence. The Red Sea Digital
Twin has its own gated roadmap in
[`projects/002_red_sea_digital_twin/roadmap.md`](../projects/002_red_sea_digital_twin/roadmap.md).

## Phase 0 — Laboratory foundation

- Reproducible ROS 2 Jazzy and Gazebo Harmonic container
- GPU-box deployment and diagnostics
- Foxglove connection from macOS
- Automated colcon build and test

## Phase 1 — Vehicle fundamentals

- Frame conventions and parameterized vehicle description
- Six-degree-of-freedom rigid-body motion
- Buoyancy, drag, current, and thruster models
- Depth and heading control
- Square waypoint mission and MCAP recording

## Phase 2 — Navigation and estimation

- IMU, pressure, compass, DVL, and surfaced GPS
- Bias, noise, dropout, and latency models
- Dead reckoning and state estimation
- Ground-truth evaluation without leaking truth into autonomy

## Phase 3 — Perception and mapping

- Underwater cameras and image degradation
- Imaging and multibeam sonar
- Bathymetric mapping and SLAM
- Loop closure and uncertainty analysis

## Phase 4 — Mission autonomy

- Mission state machine or behavior tree
- Planning, aborts, return-to-home, and fault handling
- Energy-aware decisions and adaptive sampling

## Phase 5 — Ocean science

- CTD, dissolved oxygen, turbidity, and chlorophyll sensors
- Currents, waves, tides, and water-column structure
- Reproducible scientific survey designs

## Phase 6 — Multi-vehicle systems

- Acoustic communication constraints
- Cooperative localization and coverage
- Task allocation, formations, and swarm experiments
