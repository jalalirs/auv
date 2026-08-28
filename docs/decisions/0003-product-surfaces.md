# ADR-0003: Product surfaces

- Status: Accepted
- Date: 2026-08-28

## Context

Coral City must support scientists exploring a digital twin, robotics teams
running GPU simulation, and field operators working through unreliable
connectivity. It may be deployed as a hosted service, inside an institution, or
in a hybrid arrangement. The product must support multiple concurrent users
without assigning a permanent GPU to every account.

## Options considered

1. Build one native desktop application for all uses.
2. Build an Electron application backed by cloud services.
3. Make the platform web-first, stream high-fidelity GPU applications to the
   browser, and preserve an upgrade path for a small native field shell.

## Decision

- The primary Coral City interface is a cloud-based web application.
- Browser-native 3D presents the reef atlas, environmental state, mission
  results, and other interactive scientific views that do not require an Isaac
  render process.
- High-fidelity Isaac Sim sessions run on allocated GPU compute and stream to
  authorized browser sessions through a supported low-latency streaming path.
- A compute resource broker will eventually allocate queued and interactive
  work across dedicated GPU hosts, Kubernetes, Slurm, or institutional HPC. GPU
  capacity belongs to sessions and jobs, not permanently to users.
- The field operator surface begins as an offline-capable web application
  hosted at the edge. A Tauri shell may be added later if proven native device
  access or packaging requirements justify it.
- Electron is not part of the product architecture.
- Immediate vehicle safety and emergency control remain at the field edge and
  never depend on cloud or GPU connectivity.
- Coral City is an independent product. External orchestration products are not
  assumed dependencies and are not part of its architecture.

## Consequences

- Most users need only a modern browser; institutions can deploy the same
  product privately or in a hybrid topology.
- Browser visualization and streamed simulation are distinct capabilities with
  explicit failure states.
- Authentication, tenancy, quotas, scheduling, and session isolation will need
  dedicated decisions before multi-user production deployment.
- The web application must never imply that a GPU session exists when capacity
  has not actually been allocated.
- Field operation requires local persistence and synchronization semantics in a
  later release.
