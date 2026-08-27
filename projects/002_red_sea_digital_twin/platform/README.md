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
