# GPU-box development deployment

This composition runs the current Coral City product foundation on the GPU box.
It intentionally requests no GPU because R0 contains no GPU workload yet. Future
Isaac sessions and scientific jobs will be separately allocated resources rather
than attaching a GPU to the always-on control plane or web process.

The GPU host cannot be assumed to have outbound package-registry access. The
supported development path cross-builds Linux/amd64 images on the Mac, streams
them over the existing Tailscale SSH connection, and starts the synchronized
GPU composition without pulling images:

```bash
./tools/deploy-gpu
```

The service binds to loopback by default. Set `CORAL_CITY_BIND_ADDRESS` only
when an approved network ingress is ready. Until then, use an SSH tunnel when a
Mac browser needs access. The default GPU-host port is `18088`.
