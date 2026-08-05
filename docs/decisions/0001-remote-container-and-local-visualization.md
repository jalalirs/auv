# ADR 0001: Remote container and local visualization

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

Development happens on an Apple Silicon Mac, while an x86-64 Ubuntu GPU box is
available through Tailscale. The host runs Ubuntu 20.04 and also supports other
long-lived workloads. Full remote desktops are too slow for normal operation.

## Decision

Run the project in an Ubuntu 24.04 container with ROS 2 Jazzy and Gazebo
Harmonic. Pin the workload to GPU 0. Run simulation and sensor rendering on the
GPU box, then visualize ROS data locally in Foxglove through an SSH-forwarded
WebSocket.

## Consequences

- The GPU host remains free of project-specific ROS packages.
- The Mac does not need a local ROS or Gazebo installation.
- Normal visualization avoids remote-desktop latency.
- The complete Gazebo GUI needs a separate remote-3D solution when required.
