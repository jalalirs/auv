# The box environment

- **Outcome:** one machine that is the whole platform — record, stored bytes,
  registry, control plane, and the agent that runs work — operated from a
  laptop over the tailnet.
- **Location:** `deployments/box`, driven by [`tools/box`](../../tools/box).

## Why this shape

There is one host, so there is one deployment. It is written as though there
will be more: the agent reaches the control plane over the network rather than
the loopback, images come from a registry rather than a build cache, and stored
bytes are addressed through an S3 endpoint rather than a path. **A second GPU
host joins by running the agent and being granted a queue**, and nothing here
changes.

**There is deliberately no Kubernetes.** This host already runs k3s for another
project, and dives are not scheduled by it. A dive holds a whole GPU, a lease,
and two cooperating containers that must find each other over DDS; that is an
agent's job. An agent runs equally well on bare metal, on a cloud instance, and
behind Slurm — which is the portability that matters, and the portability a
manifest would not have bought.

## What runs

| service | what it is |
| --- | --- |
| `record` | PostgreSQL with PostGIS |
| `storage` | MinIO — cities, vehicles, recorded dives |
| `registry` | vehicle images, and the autonomy images users bring |
| `control-plane` | governance and the API |
| `agent` | claims work and drives the host's container runtime |
| `console` | an operator's view of the record, not the product |

`migrate` and `bootstrap` are one-shot: the schema is applied deliberately, and
the first administrator is established once because until that happens there is
nobody to authorise it.

## Operating it

```bash
./tools/box init -email you@example.org -name "Your Name"   # once
./tools/box up
./tools/box status
./tools/box logs control-plane
./tools/box tunnel     # forward the ports to this machine
./tools/box down       # stop; volumes are kept
```

Images are **built on the box**, which has the checkout, a builder, and the
right architecture. Cross-building an amd64 image on an Apple-silicon laptop to
ship it over SSH is slower and less faithful.

## Secrets

`init` generates them **on the box** and they stay there. They are never
written to this checkout, so they cannot be committed by accident and do not
travel over SSH on every deploy. Recover the administrator's credentials with
`./tools/box secret`.

`.env.example` is the only record of what an environment needs, and carries
nothing secret.

## Ports

Published on the box's **loopback**, not its network interface, and reached by
forwarding rather than by opening a hole. Sessions travel over the tailnet
rather than TLS, which is why the session cookie is not marked secure here —
that goes back the moment there is a certificate, along with binding to a real
interface.

| | |
| --- | --- |
| api | 18080 |
| registry | 18081 |
| console | 18082 |
| storage | 19000 (console 19001) |

## What is not here yet

No simulation. The agent runs containers, but nothing yet teaches it to hold a
GPU, compose a scene, or wire a sim to an autonomy container — and the control
plane has no notion of a vehicle, a city package, a dive, or a run. Those land
on top of this, which is the right order: the orchestrator should wrap
something that already works.
