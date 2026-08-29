# Build plan

The published version of this plan, with the same content laid out for reading:
<https://claude.ai/code/artifact/909b6a1e-c6e1-457b-ba41-e4157faa7e32>

## What we are building

Isaac Sim is an engine, the way Unreal is an engine: given a scene and some
sensors, what does the robot see and how does it move. OceanSim adds underwater
sensors — an imaging sonar and a camera that models absorption and backscatter.
Together they are roughly 15% of this, and they are the part that already
exists. The rest is the platform.

## Decisions

| | |
| --- | --- |
| **Thin client** | UI, video, input. No CUDA, no ROS 2, no world data on a laptop. |
| **Agent, not Kubernetes** | GPU hosts join by running an agent. An HPC will never run kubelet for you. |
| **The queue is the resource** | Access is granted to a queue; a queue holds GPUs. Adding hardware is an insert. |
| **One GPU per dive** | Exclusive. Fractional share recorded as a number; the RTX 5880 Ada reports no MIG. |
| **One dive, two modes** | Interactive holds a stream and a human; batch does not. Same object, same scheduler. |
| **Determinism** | Definition + seed reproduces a run exactly. Replay is free, a regression is real. |
| **We publish vehicles** | Cities and vehicles are ours, versioned and granted. Users bring autonomy. |
| **Autonomy is a container** | Pinned by digest. ROS 2 over DDS. Contract checked at admission. |
| **Nothing mutates** | A run pins city, vehicle, autonomy, conditions, seed, and runtime version. |
| **Storage** | Object store is origin; each node keeps a content-addressed cache. |
| **Recording tiers** | Telemetry always (MB). Sensor frames on request (GB/min). |

## Milestones

| | | done when | cost |
| --- | --- | --- | --- |
| **M1** | The control plane knows what a dive is | a granted city is listed and an ungranted one is not | 2–3d |
| **M2** | Assets are real packages | a node syncs a city by digest, fetching only what it lacks | 2d |
| **M3** | The vehicle behaves like a submarine | the ROV holds depth against real buoyancy, gravity on | 3–4d |
| **M4** | A dive runs end to end | submit → GPU claimed → sim runs → telemetry → replay reproduces it | 4d |
| **M5** | Autonomy plugs in | a container we did not write holds 2 m depth over ROS 2 | 3d |
| **M6** | The client | Coral City opens with no trace of Isaac Sim's editor | 1w |
| **M7** | Batch | one dive × 200 conditions, headless, scored | 3d |

M3 carries the risk: everything else is plumbing, that is physics that has to
be right.

## Not in this plan

Real reefs from bathymetry and photogrammetry, and forcing from GLORYS12 and
ERA5. Both matter; both are content pipelines that land on a platform that
works. The MHL test tank is enough to build every milestone above.
