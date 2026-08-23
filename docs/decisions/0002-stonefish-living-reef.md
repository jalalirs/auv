# 0002 — Stonefish for the open living-reef track

- Status: accepted
- Date: 2026-08-23

## Context

The first DAVE world proves ROS 2, ArduSub, MAVROS, Gazebo, camera, and sonar
plumbing, but its visual environment and interactive frame rate are not a good
daily exploration experience. The next simulator needs credible underwater
vehicle physics, useful perception sensors, ROS 2 Jazzy compatibility, richer
rendering, and a practical remote display path.

## Decision

Use Stonefish 1.6 as the first advanced open simulator track. Build it in a
separate pinned container, start with the unofficial MBARI MOLA and coral
assets, repair known scene defects locally, add explicitly labelled scripted
fauna, and stream the native OpenGL GUI with VirtualGL EGL plus Xpra.

DAVE remains the ArduSub/Gazebo integration checkpoint. It is not the visual
reference world.

## Alternatives considered

- **HoloOcean 2.3** has strong Unreal Engine visuals, Fossen dynamics, sonar,
  several AUVs, and multi-agent support. Its simulator repository requires an
  Epic-linked GitHub account, which the GPU box cannot currently access, and
  its documented ROS 2 bridge targets Humble rather than Jazzy.
- **OceanSim 0.2** provides a modern Isaac Sim/OpenUSD perception stack,
  synthetic underwater camera and acoustic sensors, terrain generation, and
  ROS 2. It is attractive for a later perception/digital-twin track, but is not
  yet our primary validated vehicle-hydrodynamics environment.
- **UNav-Sim** provides Unreal/AirSim underwater rendering and a BlueROV2, but
  its environment build and asset workflow are heavier and less direct for the
  current headless GPU-to-Mac setup.

## Consequences

- We gain a real marine-robotics physics/rendering engine immediately without
  waiting for a private game-engine download.
- The simulator's GPL-3.0 image remains separate from the repository's future
  license decision.
- MOLA dynamics must be identified and validated before model-based control
  results are treated as representative of the physical vehicle.
- Moving fish are semantic actors, not hydrodynamic agents. Schooling behavior
  and animal interaction will be a later explicit subsystem.
