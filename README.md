# AUV Lab

A long-lived laboratory for autonomous underwater vehicles, marine robotics,
ocean sensing, and ocean engineering.

This repository is both a working ROS 2 system and a record of the journey:
simulation code, controls, navigation, perception, experiments, research notes,
and reproducible results belong here. Large datasets, recordings, model weights,
and generated build artifacts do not.

## Current milestone

Project 001 starts with a sonar-equipped BlueROV2 Heavy beside a sunken ship in
DAVE. The first runnable checkpoint streams its camera, sonar, navigation, and
vehicle state from the GPU box into Foxglove on the Mac. It then grows into a
vehicle that can:

1. hold a commanded depth and heading;
2. reject a simple current disturbance;
3. follow a square waypoint mission;
4. estimate its state from noisy sensors;
5. record the mission as MCAP; and
6. compare estimated state with simulator ground truth.

## Execution model

- **Mac:** editing, orchestration, Foxglove, analysis, and documentation.
- **GPU box:** versioned Ubuntu container, ROS 2 Jazzy, Gazebo Harmonic, simulation,
  rendering, and later perception workloads.
- **Transport:** Git and SSH over Tailscale. Visualization uses an SSH-forwarded
  Foxglove WebSocket rather than a remote desktop for normal operation.
- **GPU:** workloads are pinned to GPU 0 by default.

## Repository map

| Path | Purpose |
| --- | --- |
| `ros2_ws/src` | Canonical ROS 2 workspace and packages |
| `docker` | Reproducible ROS/Gazebo development image |
| `tools` | Human-facing local and remote commands |
| `labs` | Guided exercises that teach one concept at a time |
| `experiments` | Reproducible, measurable investigations |
| `analysis` | Non-ROS analysis library and notebooks |
| `research` | Bibliography, reading list, and original notes |
| `docs` | Roadmap, architecture, concepts, decisions, and lab log |
| `data` | Ignored local/remote datasets, recordings, and models |

See [docs/architecture.md](docs/architecture.md) for the system boundary and
[docs/roadmap.md](docs/roadmap.md) for the learning sequence.

## Commands

```bash
make doctor       # inspect local tools and remote GPU capacity
tools/gpu sync "describe the change"  # commit and sync Mac, GitHub, and GPU
# Or: make sync MESSAGE="describe the change"
make dive         # launch the headless First Dive scene on the GPU
make dive-status  # inspect its container state
make dive-topics  # inspect its live ROS graph
make dive-logs    # follow simulator startup and runtime logs
make view         # open the SSH tunnel and Foxglove on the Mac
make drive        # open the browser joystick for manual control
make drive-stop   # close the browser joystick tunnel
make dive-stop    # stop the First Dive scene
make build        # build the versioned ROS/Gazebo container remotely
make up           # start the remote development container
make shell        # open a shell in the remote container
make test         # build and test the ROS workspace remotely
make down         # stop the AUV container
```

See [labs/03_first_dive/README.md](labs/03_first_dive/README.md) for the scene,
expected topics, and completion check.

Copy `.env.example` to `.env` only when overriding defaults. Never commit
credentials or tokens.

The GPU box cannot reach GitHub directly. `tools/gpu sync` therefore pushes the
commit to GitHub and to a private bare Git mirror over Tailscale, then
fast-forwards `~/auv` from that mirror. It refuses divergent histories,
uncommitted GPU edits, and non-fast-forward updates. Remote build and run
commands also refuse to proceed until the Mac and GPU commit IDs match.

## Repository rules

- `ros2_ws` is the only ROS workspace.
- Generated `build`, `install`, and `log` directories are ignored.
- Raw experimental data is immutable; derived results must be reproducible.
- Bags, MCAP files, datasets, weights, and large renders remain outside Git.
- Paper PDFs are not committed. Store citations, stable links, and our notes.
- Runtime assets live in the ROS package that owns them.
- New packages are created only when a working milestone requires them.
- Avoid generic dumping grounds such as `misc`, `temp`, or `scripts`.

## License

No repository license has been selected yet. ROS package manifests use
`Proprietary` as a deliberate placeholder until that decision is made.
