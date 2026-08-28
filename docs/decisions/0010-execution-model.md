# ADR-0010: Execution model

- Status: Accepted
- Date: 2026-08-28

## Context

The platform runs finite scientific work — ingestion, reconstruction,
environmental models, analysis — and will later run interactive GPU simulation
sessions. Work must eventually be placed on a development workstation,
Kubernetes, Slurm, and institutional HPC without changing the domain.

Organisations will supply their own autonomy containers. Scarce GPUs must not
be held permanently by a user who left a browser tab open, and refusals must be
explainable.

## Options considered

1. Execute work inside the control plane.
2. Adopt an existing workflow orchestration engine immediately.
3. A first-class job model with pluggable execution targets and separate
   leased workers.

## Decision

- **Job** — one finite containerised execution. Declares an image *digest*
  (never a tag), command, checksummed inputs, outputs with destinations and
  size caps, a resource request, an owning organisation, and the recipe that
  produced the spec.
- **JobAttempt** — one placement onto a target. Retries create attempts, never
  new jobs, so provenance stays singular.
- **JobEvent** — durable and sequence-numbered: `admitted`, `scheduled`,
  `started`, `progress`, `output_received`, `succeeded`, `failed`, `cancelled`,
  `evicted`, `timed_out`.
- **ExecutionTarget** — one Go interface with several adapters, in build order
  `local-docker`, then Kubernetes, Slurm, and institutional HPC:

  ```go
  type Target interface {
      Submit(ctx, JobSpec)   (Placement, error)
      Poll(ctx, Placement)   (State, error)
      Cancel(ctx, Placement) error
      Logs(ctx, Placement)   (io.ReadCloser, error)
  }
  ```

- **Broker.** On submit, consult the ADR-0005 decision point, then quota, then
  target capacity. Write an admission or a refusal carrying a reason. Both are
  rows. There is no silent queueing and no silent starvation.
- **Worker** — a separate binary that leases work with a token and a heartbeat.
  A dead worker's lease expires and its attempt is reclaimed. **The control
  plane never executes scientific work.**
- **Interactive sessions** use the same broker with a different lifecycle:
  lease, heartbeat, idle expiry, forced reclaim, and per-session scoped
  streaming credentials.
- **Organisation-supplied containers are untrusted.** No host network, no
  privileged mode, read-only mounts except declared outputs, egress policy,
  seccomp profile, and enforced resource caps. This is settled before the first
  externally supplied stack runs.
- **No workflow DAG engine** until at least two real multi-step pipelines exist
  to run through it.

## Consequences

- Moving work to a cluster is an adapter, not a redesign.
- Worker failure is recoverable without operator intervention, and outputs are
  recorded exactly once.
- "Why was my job refused" is answerable from data.
- Exactly-once output handling and lease expiry must be tested by fault
  injection, not by inspection.
- Multi-step pipelines are expressed by hand until an engine is justified.
