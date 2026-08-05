# E001 — Depth hold under current

- **Status:** Planned
- **Question:** Can the initial controller maintain commanded depth under a
  constant horizontal current and noisy pressure measurements?

## Procedure

1. Start from rest at the surface.
2. Command the target depth from `experiment.yaml`.
3. Introduce the configured current after settling.
4. Record commands, observations, estimated state, ground truth, and diagnostics.
5. Evaluate the run using the pinned metrics below.

## Metrics

- rise time;
- percent overshoot;
- steady-state depth error;
- RMS depth error after current onset; and
- integrated absolute control effort.

Recordings belong under `/data/recordings/e001_depth_hold`. Commit only the
configuration, analysis code, small figures, and interpretation.
