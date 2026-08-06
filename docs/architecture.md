# Architecture

The Mac is the control and visualization surface. The GPU box is a replaceable
execution target, not the source of truth.

```mermaid
flowchart LR
    Mac["Mac: code, Foxglove, analysis"]
    Git["Git repository"]
    Box["GPU box: Docker on Ubuntu 20.04"]
    Stack["Ubuntu 24.04 container: ROS 2 Jazzy + Gazebo Harmonic"]
    Data["External runtime data"]

    Mac --> Git
    Git -->|"verified Git mirror over Tailscale"| Box
    Box --> Stack
    Stack -->|"Foxglove WebSocket through SSH tunnel"| Mac
    Stack --> Data
```

## Boundaries

- The host operating system provides Docker, NVIDIA drivers, storage, and
  networking. Project dependencies are not installed directly on it.
- The container owns ROS, Gazebo, bridge processes, and development tools.
- The repository owns source, small assets, configuration, and documentation.
- `/data` owns recordings, datasets, model weights, and generated artifacts.
- Simulation truth is available to evaluation tooling but not to autonomy nodes.

## Networking

The container uses host networking so ROS discovery remains local to the GPU
box. The Mac does not join the ROS DDS domain directly. Foxglove Bridge exposes
one WebSocket endpoint on remote port 8765, forwarded to the Mac through SSH on
local port 18765. Keeping the ports distinct avoids a known local conflict with
Claude Science's default application port.

## Visualization

Foxglove is the daily interface for transforms, robot geometry, camera feeds,
sonar, maps, plots, controls, and playback. Gazebo uses EGL for GPU rendering
without an X server. A separate VirtualGL/TurboVNC path may later expose the
complete Gazebo GUI for world editing and inspection.
