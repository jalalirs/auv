# Isaac and underwater compatibility

- Decision date: 2026-08-27
- Canonical target: **Isaac Sim 6.0.1**
- Evaluation target: **Isaac Sim 5.1.0 only when needed to study existing
  underwater work**

## Runtime matrix

| Concern | Canonical foundation | Underwater compatibility lab | Current GPU host |
| --- | --- | --- | --- |
| Isaac Sim | 6.0.1, current supported release | 5.1.0, unsupported | 6.0.1 image pulled; checker passed |
| Ubuntu | 24.04 LTS | 22.04/24.04 supported by NVIDIA | 20.04.6; unsupported by NVIDIA |
| Python | 3.12 | 3.11 | System version is irrelevant inside the pinned runtime |
| NVIDIA driver | 595.58.03 listed in requirements | 580.65.06 listed for 5.1 | 580.126.09; 6.0.1 checker passed |
| ROS 2 | Jazzy; Humble also tested | Humble or Jazzy | Existing projects vary |
| Deployment | Linux container or clean workstation | Disposable Linux container | Isolated GPU 1 container approved for M0 |
| macOS display | WebRTC client 2.0.0, Apple Silicon build | WebRTC client available | Tailscale path exists |
| OpenUSD | Canonical scene contract; validate with target runtime | Import-only compatibility check | Project assets remain runtime-independent |
| Lifecycle | Security and migration baseline | Throwaway porting reference | No in-place platform mutation |

NVIDIA's current download page lists Isaac Sim 6.0.1 and WebRTC client 2.0.0.
The [6.0 Python installation](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html)
requires Python 3.12, while the
[5.1 environment](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html)
uses Python 3.11. NVIDIA recommends ROS 2 Humble and Jazzy in the
[current ROS integration guide](https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/ros2_landing_page.html).

The supported [WebRTC livestream client](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html)
has a macOS installation and is intended for a headless Isaac instance. We use
it through Tailscale rather than sending a full remote desktop. One client may
connect to an Isaac instance at a time.

## Underwater projects

| Project | Target observed | Useful capability | Fidelity boundary | Adoption status |
| --- | --- | --- | --- | --- |
| [OceanSim](https://github.com/umfieldrobotics/OceanSim) | Main targets Isaac Sim 5.0; Python follows Isaac | Underwater camera, imaging sonar, DVL, barometer, GPU perception pipeline | Perception framework, not a validated whole-vehicle or ocean-dynamics twin | Evaluate and port behind adapters; BSD-3-Clause |
| [GRAAL OceanSim fork](https://github.com/GRAAL-Lab/OceanSim) | Used with the GRAAL 5.1 stack | Practical 5.1 integration reference | Fork-specific behavior and assets must be reproduced and validated | Compatibility lab only; BSD-3-Clause |
| [IsaacSim Underwater](https://github.com/GRAAL-Lab/IsaacSim_Underwater) | Isaac Sim 5.1, Python 3.11 | Fossen-style 6-DOF hydrodynamics, thrusters, BlueROV, camera, 2D/3D sonar, DVL, depth, IMU, ROS 2 | 3D sonar uses an RTX ray-intersection approximation; it is not full acoustic propagation, phase, or multipath | Study interfaces only; no repository license was found, so code/assets cannot be copied or distributed |

Audited revisions are pinned in `runtime.yaml`; a future evaluation must use
those revisions or update this report before comparing results.

## What enters the foundation

- OpenUSD site composition, scale, coordinates, semantics, and provenance
- Project-owned ROS 2 topic and frame contracts
- Project-owned environmental and sensor configuration schemas
- Versioned adapters whose upstream revision and license are explicit
- Separate validation levels for visual plausibility, robotics usefulness, and
  scientific fidelity

## What does not enter the foundation

- An OceanSim or GRAAL internal data model as the project schema
- Unlicensed third-party code or downloaded asset bundles
- A claim that RTX lidar points are physically accurate multibeam sonar
- A claim that attractive underwater rendering is a calibrated optical model
- USD layers that require a research extension merely to open the reef site
- An unsupported Isaac release as a production dependency

## OpenUSD compatibility policy

Canonical reef and site layers use standard OpenUSD composition and explicitly
author units, up axis, local frame metadata, asset identifiers, and source
provenance. Isaac-specific physics and sensor schemas live in separate runtime
layers. Each supported runtime must open and validate the canonical site before
an adapter is accepted.

## Porting order

1. Launch a plain project-owned USD scene under Isaac 6.0.1.
2. Prove WebRTC streaming to the Mac and record performance.
3. Add ROS 2 Jazzy clock, transforms, and a trivial command interface.
4. Port OceanSim camera effects as the first bounded adapter.
5. Evaluate DVL and imaging sonar against documented test scenes.
6. Implement project-owned hydrodynamics and thrusters from published models,
   using third-party behavior only as comparative evidence.
7. Add acoustic complexity in validation stages rather than labeling a ray
   caster as final sonar.
