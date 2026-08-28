# Coral City

Coral City is a Red Sea digital-twin, ocean-science, simulation, and autonomous
marine-robotics platform. This repository is its monorepo.

The system will turn real surveys and environmental observations into a
traceable, time-aware 3D reef; run scientific forecasts and scenarios; let
robots rehearse missions in simulation; deploy approved missions through a
field-safe edge station; and return observations to the twin as new evidence.

## Repository map

| Area | Responsibility |
| --- | --- |
| `apps/` | Interfaces used by scientists and field operators |
| `services/` | Coral City product logic and stable APIs |
| `packages/` | Shared, versioned contracts and clients |
| `workflows/` | Finite scientific and data-processing jobs |
| `integrations/` | Thin boundaries to Isaac, ROS 2, and scientific models |
| `deployments/` | Reproducible local, GPU, edge, and HPC deployment definitions |
| `catalog/` | Small, versioned manifests for data and artifacts |
| `docs/` | Vision, architecture, roadmap, and reviewed decisions |
| `tools/` | Human entry points for repository operations |

There is no `projects/` layer. Coral City is the project.

## Non-negotiable boundaries

- Git stores code, contracts, manifests, recipes, and small evidence records.
- Git does not store raw survey video, large meshes, point clouds, NetCDF,
  Zarr, ROS bags, model outputs, or renders.
- Observations are immutable. Corrections create new versions.
- Every derived artifact must identify its source, processing recipe, software
  version, checksums, coordinates, time basis, truth class, and uncertainty.
- Isaac Sim is a simulation and presentation runtime, not the scientific
  archive or control plane.
- ROS 2 owns robot communication and autonomy integration, not product data.
- Scientific solvers run behind adapters and never define Coral City APIs.
- Vehicle safety and low-latency control remain local to the field edge.

## Developer commands

Install [mise](https://mise.jdx.dev/) once, then enter the repository and run:

```bash
mise trust
mise install
just setup
just check
just test
```

Mise pins the executable toolchains. Just is the small repository command
surface. pnpm manages TypeScript workspaces only; Go, C++, Rust, and scientific
software retain their native build systems.

## Current state

The monorepo structure, architectural contracts, language policy, product
surfaces, and developer toolchain are prepared. Product runtime code begins in
R0 checkpoint 3.

## Synchronization

The Mac checkout, GitHub, and GPU checkout are synchronized with either:

```bash
./tools/gpu sync "describe the approved change"
just sync "describe the approved change"
```

The previous repository is recoverable from Git tag
`legacy-before-restart-2026-08-28`.

Start with [the vision](docs/vision.md), [system architecture](docs/architecture.md),
[release roadmap](docs/roadmap.md), and [development rules](docs/development.md).
