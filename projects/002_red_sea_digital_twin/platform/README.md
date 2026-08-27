# Platform

This directory records the reproducible runtime boundary for the Red Sea
Digital Twin. It separates the long-lived project contract from experiments
with rapidly changing simulation releases.

## Current decision

- The canonical development target is Isaac Sim 6.0.1 on Ubuntu 24.04 with
  ROS 2 Jazzy.
- The present shared GPU host passed the Isaac 6.0.1 compatibility checker for
  an isolated GPU 1 container; a host OS upgrade is not required for M0.
- Isaac Sim 5.1, OceanSim, and IsaacSim Underwater may be evaluated in a
  disposable compatibility lab; they are not foundation dependencies.
- No host operating-system, driver, storage, or service changes are performed
  without a separately approved maintenance and rollback plan.

## Documents

- [GPU host readiness](gpu-host-readiness.md)
- [Isaac and underwater compatibility](isaac-compatibility.md)
- [Machine-readable runtime pin](runtime.yaml)
- [Compatibility audit](audits/2026-08-27-isaac-6.0.1-compatibility.md)

## Launch the M0 calibration scene

The launcher runs Isaac Sim on GPU 1, opens the project-owned calibration USD,
and serves the native WebRTC stream through the GPU host's Tailscale address.
It never opts in to NVIDIA telemetry.

1. Read and accept the NVIDIA Omniverse EULA.
2. Set `ISAAC_ACCEPT_EULA=Y` in the ignored local `.env` file.
3. Synchronize and launch:

   ```bash
   ./tools/gpu sync "add Isaac WebRTC launcher"
   ./tools/isaac check
   ./tools/isaac up
   ./tools/isaac status
   ```

4. In NVIDIA Isaac Sim WebRTC Streaming Client 2.0.0 for macOS, connect to
   `100.76.65.1`. Tailscale must be connected. The signaling and media ports
   are TCP 49100 and UDP 47998.

Use `./tools/isaac logs` to follow startup and `./tools/isaac stop` to release
GPU memory. The first launch can take several minutes while shaders compile.
