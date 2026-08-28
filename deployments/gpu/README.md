# GPU-box development deployment

This composition runs the current Coral City product foundation on the GPU box.
It intentionally requests no GPU because R0 contains no GPU workload yet. Future
Isaac sessions and scientific jobs will be separately allocated resources rather
than attaching a GPU to the always-on control plane or web process.

Run from the repository root on the GPU box:

```bash
docker compose -f deployments/gpu/compose.yaml up --build -d --wait
```

The service binds to loopback by default. Set `CORAL_CITY_BIND_ADDRESS` only
when an approved network ingress is ready.
