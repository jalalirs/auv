# Deployments

Reproducible desired state for each execution environment lives here. Secrets,
large datasets, runtime caches, and machine-specific credentials do not.

Current executable deployments:

- [`local`](local/README.md): complete R0 runtime on a developer machine;
- [`gpu`](gpu/README.md): the same foundation on the GPU box without claiming a
  GPU prematurely.

The `edge` and `hpc` areas remain documented boundaries only until their release
requirements are approved.
