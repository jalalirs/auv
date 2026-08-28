# Release roadmap

These are complete operational releases, not proofs of concept. Experiments,
spikes, and technology tests may happen inside a release but never satisfy its
gate by themselves.

## R0 — Monorepo and engineering foundation

**Outcome:** The team can understand, build, test, synchronize, and operate the
approved system structure consistently on Mac and GPU.

**Includes:**

- reviewed architecture and decision process;
- approved technology stack;
- monorepo task runner and dependency policy;
- continuous validation;
- local/GPU development environments;
- secrets and large-data boundaries; and
- operational documentation.

**Gate:** A new contributor can clone the repository, understand every top-level
area, run the approved checks, and synchronize a harmless change without hidden
manual setup.

**Current evidence:** pinned Mac/GPU toolchains; root setup/check/test/run/sync
commands; Go control-plane contract tests; TypeScript UI state tests; production
web and Go container builds; public-ingress end-to-end validation; continuous
checks; and synchronized checkpoint commits.

## R1 — Scientific Reef Atlas

**Outcome:** A scientist can add an authorized reef survey, inspect a
scientifically honest 3D site at real scale, trace every displayed artifact to
its evidence, and compare published site versions without editing code.

**Includes:** immutable survey intake, reconstruction and quality control,
coordinate/datum/scale enforcement, versioned 3D products, provenance, web and
Isaac exploration, publication, restoration, and comparison.

**Gate:** A new survey proceeds from one approved manifest to a reproducible,
validated, explorable reef version with complete evidence and documented
performance.

## R2 — Environmental State and Forecast System

**Outcome:** A scientist can view and compare observations, analyses, forecasts,
and scenarios around a reef for a selected time window.

**Includes:** sensor and forecast ingestion, canonical environmental packages,
model adapters, uncertainty, spatial/time alignment, historical replay,
monitoring, and scientific validation.

**Gate:** One site can reproduce a documented environmental event from pinned
inputs and then issue a versioned forecast or scenario without confusing truth
classes.

## R3 — Autonomous Mission Simulation Laboratory

**Outcome:** A robotics team can design, run, compare, and reproduce AUV missions
inside a measured reef and versioned environmental state.

**Includes:** vehicle and sensor models, Isaac/ROS integration, perception,
SLAM, planning, control, mission evaluation, batch experiments, and repeatable
reports.

**Gate:** An autonomy stack completes a standard mission suite under controlled
environmental variation, with objective metrics and reproducible evidence.

## R4 — Field Mission System

**Outcome:** An operator can safely prepare, execute, monitor, interrupt, and
recover a real mission while Coral City captures complete evidence.

**Includes:** field edge station, offline operation, safety policy, vehicle
integration, mission packages, telemetry synchronization, incident handling,
and field runbooks.

**Gate:** A supervised field exercise completes safely through a documented
connectivity-loss scenario and synchronizes a complete mission record.

## R5 — Operational Red Sea Digital Twin

**Outcome:** Multiple reef sites, models, sensor networks, vehicles, and partner
institutions operate through one governed platform.

**Includes:** multi-site scaling, institutional identity, access governance,
production observability, disaster recovery, data lifecycle policy, partner
APIs, and sustained scientific operations.

**Gate:** The platform operates agreed sites and workflows against service,
scientific-quality, security, and recovery objectives for a sustained review
period.

## Release rule

A release closes only when its user-visible outcome and gate pass against a
versioned candidate with preserved evidence. Schedule pressure does not convert
unfinished work into a completed release.
