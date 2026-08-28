# Local deployment

The whole platform on a developer's machine: PostgreSQL with PostGIS, an
S3-compatible object store, the control plane, a worker that runs real
containers, and the web application.

```bash
just run     # build and start everything
just e2e     # check it end to end
just logs    # watch it
just stop    # stop, keeping what it holds
just reset   # stop and discard everything
```

`just run` prints where to sign in. The administrator and storage credentials
here are development defaults, stated openly in `compose.yaml`; the GPU
deployment requires real ones.

## The worker and the host's container runtime

The worker drives the host's container runtime through its socket, so a bind
mount it asks for is resolved by the daemon on the host rather than inside the
worker. That is why it is told both where it stages work
(`CORAL_CITY_WORKER_WORKDIR`) and what that same directory is called on the host
(`CORAL_CITY_WORKER_HOST_WORKDIR`): the two are different strings for one
directory, and a job would read an empty one if they were confused.

## Ports

| Port | What |
| --- | --- |
| 18090 | the web application |
| 18089 | the control plane, for tooling and the end-to-end check |
| 19000 | the object store, which presigned URLs name |

18088 is deliberately left alone: it is where `coral` forwards the GPU host.
