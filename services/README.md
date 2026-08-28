# Services

Long-running Coral City processes.

| Service | What it owns |
| --- | --- |
| `control-plane/` | Identity, governance, places, layers, provenance, work, and the record of all of it |
| `worker/` | Leasing work and running it as a container |

They are separate because the control plane must never run scientific work. A
worker's failure is recoverable — its lease expires and the work is returned to
the queue — and that is only true because the thing that admits work is not the
thing that runs it.
