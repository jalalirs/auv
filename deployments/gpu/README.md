# GPU deployment

The whole platform on the shared GPU host.

## What this host is

A shared workstation. It runs other people's production containers alongside
this, its root filesystem is largely full, and it cannot reliably reach a
package registry. Every choice here follows from that:

- every container declares a processor and memory limit, so that neither a
  reconstruction job nor the platform that admitted it can take the machine
  down;
- stored bytes go to `IOCEAN_STORAGE_PATH`, a path the operator chooses on a
  filesystem with room, because Docker cannot bound a named volume and growth
  here must not become somebody else's outage;
- images are built on a developer's machine for this host's architecture and
  streamed over the existing SSH connection. Nothing pulls.

It currently uses no accelerator. Nothing in this deployment needs one yet.

## Settings this deployment requires

Unlike the local deployment, nothing here has a development default. A
credential that ships in a file is not a credential.

| Variable | Meaning |
| --- | --- |
| `IOCEAN_DATABASE_PASSWORD` | the record's password |
| `IOCEAN_STORAGE_ACCESS_KEY` | the object store's access key |
| `IOCEAN_STORAGE_SECRET_KEY` | the object store's secret key |
| `IOCEAN_STORAGE_PATH` | where stored bytes live, on a filesystem with room |
| `IOCEAN_ADMIN_EMAIL` | the first administrator |
| `IOCEAN_ADMIN_SECRET` | their sign-in secret |
| `IOCEAN_ADMIN_NAME` | their display name |
| `IOCEAN_ADMIN_ORG` | the first institution's short name |

## Deploying

```bash
./tools/deploy-gpu
```

It refuses to run against an uncommitted working tree, because the host serves
what is in Git.

## Reaching it

```bash
coral
```

Then <http://localhost:18088>. The tunnel forwards the application on 18088 and
stored bytes on 19000; both are needed, because a presigned URL is signed over
its host and so cannot be proxied through the application's port.
