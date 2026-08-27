# 0004 — Pin the canonical Isaac runtime

- Status: accepted
- Date: 2026-08-27

## Context

Isaac Sim 6.0.1 is the current supported release, while the underwater projects
we want to learn from target Isaac Sim 5.0 or 5.1. The available GPU host runs
Ubuntu 20.04 and NVIDIA driver 580.126.09. It also carries active Docker and
K3s services, stateful data, and other GPU workloads.

Building the twin directly on the older underwater stack would produce quick
visual results but would make unsupported software and third-party internal
schemas foundational. Upgrading the shared host in place would create an
unacceptable recovery and service-continuity risk.

## Decision

Pin the Project 002 canonical runtime to:

- Isaac Sim 6.0.1;
- Ubuntu 24.04 LTS on x86_64;
- NVIDIA driver 595.58.03, the version tested by NVIDIA for this release;
- Python 3.12;
- ROS 2 Jazzy; and
- NVIDIA Isaac Sim WebRTC Streaming Client 2.0.0 for macOS.

OpenUSD remains the canonical scene contract. Site data and project schemas
must not require OceanSim, IsaacSim Underwater, or any single Isaac release to
open.

Isaac Sim 5.1 and its compatible underwater projects form a disposable
compatibility lab only. Their behavior may inform adapters and validation, but
the project does not backport its foundation to them. Code or assets without a
clear redistribution license are not copied.

The shared Ubuntu 20.04 host is not approved for the canonical runtime. Any OS,
driver, disk, or service change requires a separately approved maintenance,
backup, console-recovery, and rollback plan.

## Upgrade policy

- Patch releases may advance after the minimal scene, ROS, streaming, and
  project extension checks pass in a clean environment.
- Minor or major releases require a compatibility branch and an updated matrix
  before the canonical pin changes.
- Experiments record exact Isaac, extension, container, asset, scenario, and
  source revisions.
- Unsupported releases are removed from the canonical support window; they may
  remain only as reproducibility archives.

## Consequences

- The first deployment waits for a clean, supported, recoverable environment.
- OceanSim and IsaacSim Underwater need explicit 6.0 porting evaluation.
- Project contracts remain useful if an underwater extension disappears or
  Isaac changes APIs.
- We avoid risking unrelated services for a simulation installation.
- The first successful scene will be small and plain by design; reef fidelity
  is added after the runtime and streaming path are reproducible.
