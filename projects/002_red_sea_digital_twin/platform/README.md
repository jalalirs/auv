# Platform

This directory records the reproducible runtime boundary for the Red Sea
Digital Twin. It separates the long-lived project contract from experiments
with rapidly changing simulation releases.

## Current decision

- The canonical development target is Isaac Sim 6.0.1 on Ubuntu 24.04 with
  ROS 2 Jazzy.
- The present shared GPU host is not approved for that runtime yet.
- Isaac Sim 5.1, OceanSim, and IsaacSim Underwater may be evaluated in a
  disposable compatibility lab; they are not foundation dependencies.
- No host operating-system, driver, storage, or service changes are performed
  without a separately approved maintenance and rollback plan.

## Documents

- [GPU host readiness](gpu-host-readiness.md)
- [Isaac and underwater compatibility](isaac-compatibility.md)
- [Machine-readable runtime pin](runtime.yaml)
