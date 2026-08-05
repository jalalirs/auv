# 2026-08-05 — Foundation

## Established

- Chose ROS 2 Jazzy with Gazebo Harmonic as the conservative baseline.
- Selected the remote GPU box for Linux execution and GPU rendering.
- Reserved GPU 0 for AUV work by default.
- Selected Foxglove over remote desktop for daily visualization.
- Created the initial repository and experiment structure.

## Infrastructure observations

- GPU 0 has approximately 27 GiB free VRAM while existing services are idle.
- The host has 48 logical CPUs and approximately 125 GiB RAM.
- Storage cleanup increased free disk space to approximately 204 GB.

## Next step

Build the container and prove the complete path with a minimal Gazebo world,
Foxglove Bridge, and one observable moving frame.
