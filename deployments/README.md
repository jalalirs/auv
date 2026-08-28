# Deployments

| Deployment | What it is |
| --- | --- |
| `local/` | The whole platform on a developer's machine |
| `gpu/` | The whole platform on the shared GPU host |

Both run the same components in the same shape: the record, the object store,
the control plane, a worker, and the web application. Nothing in the local
deployment is a stand-in for something that would be different in production,
because a stand-in hides exactly the problems worth finding.

## Applying the schema

Applying a schema change is a deliberate act, never something a serving process
does on startup: a service that migrated as it booted would change the record
every time it was restarted, including by accident. The `migrate` service runs
to completion first, and the control plane waits for it.

A build whose migrations have not been applied reports itself **not ready**,
because serving against an older schema would write records this build's rules
were never checked against.

## Bootstrapping

`bootstrap` establishes the first administrator — the one act that cannot go
through the API, because until it happens there is nobody to authorise it. It
also provisions the worker, whose credential cannot be recovered once issued and
is therefore written to a file the worker reads.

It is idempotent. The local deployment supplies development credentials; the GPU
deployment requires them to be given.

## The GPU host

It is a shared workstation, not a cluster: two accelerators, a root filesystem
that is largely full, and roughly thirty containers belonging to other projects.
So every container there declares a processor and memory limit, stored bytes go
to a path the operator chooses on a filesystem with room, and images are built
elsewhere and streamed in, because that host cannot reliably reach a registry.

```bash
./tools/deploy-gpu   # build for its architecture, stream, migrate, start, check
coral                # forward its ports to this machine
```

The tunnel forwards two ports, not one. The application is reached on the first;
stored bytes are read and written directly on the second, because a presigned
URL is signed over its host and cannot be proxied through the first.
