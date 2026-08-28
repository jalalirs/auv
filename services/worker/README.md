# Worker

The worker takes admitted work from the control plane and runs it as a
container.

## What it is allowed to do

A worker authenticates as a service principal holding `admin` over the **work
queue** — a scope of its own, separate from the platform. It therefore cannot
read a city, contribute a layer, submit work, or act for an organisation.

Everything it touches while running a job, it reaches through the lease it holds
on that job:

- input bytes, through `POST /api/v1/work/{attempt}/inputs`;
- output storage, through `POST /api/v1/work/{attempt}/uploads`.

A worker that is not currently running a job can reach neither.

## How a job is run

Work supplied by an organisation is untrusted. Every container runs with no
network, no capabilities, no way to gain privileges, a read-only root
filesystem, a bounded temporary filesystem, a process limit, and exactly the
processor and memory the job was admitted for.

Inputs are staged read-only and verified against the digests the job's
provenance names; a mismatch fails the attempt rather than running against
different bytes. Only the outputs the job declared are collected, and only
within the sizes it declared.

## Recovering from a worker that dies

A worker holds an attempt by a lease it must keep renewing. If it stops — a
crash, a lost network, a terminated host — the lease expires and the control
plane returns the work to the queue as a new attempt, up to the retry limit.
Nothing has to be noticed by a person for this to happen.

If the platform reclaims an attempt while the worker is still running it, the
worker learns this from its next heartbeat and stops, rather than writing
results the platform has already given to someone else.

## Settings

| Variable | Meaning |
| --- | --- |
| `CORAL_CITY_CONTROL_PLANE_URL` | where work is leased from (required) |
| `CORAL_CITY_WORKER_CREDENTIAL` | this worker's service credential (required) |
| `CORAL_CITY_WORKER_TARGET` | the execution target this worker serves |
| `CORAL_CITY_WORKER_WORKDIR` | where inputs and outputs are staged |
| `CORAL_CITY_WORKER_HOST_WORKDIR` | the same directory as the container runtime sees it |
| `CORAL_CITY_DOCKER_SOCKET` | the container runtime's local socket |
| `CORAL_CITY_WORKER_POLL_INTERVAL` | how long to wait when there is no work |
| `CORAL_CITY_WORKER_HEARTBEAT_INTERVAL` | how often to renew a lease |
| `CORAL_CITY_WORKER_MAX_INPUT_BYTES` | the largest single input to stage |

`CORAL_CITY_WORKER_HOST_WORKDIR` matters when the worker itself runs in a
container: a bind mount is resolved by the container runtime on the host, so the
path the worker writes to and the path the daemon mounts from are not the same
string.
