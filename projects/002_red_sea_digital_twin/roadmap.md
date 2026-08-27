# Roadmap and gates

Progress is gate-based. Calendar estimates are planning aids, not acceptance
criteria.

## M0 — Foundation and compatibility spike

- Approve the GPU host upgrade and storage plan.
- Pin an Isaac Sim release and prove supported remote streaming to macOS.
- Create a minimal OpenUSD stage through a reproducible command.
- Evaluate OceanSim and IsaacSim Underwater without adopting their data models.
- Record licensing and compatibility findings.

**Gate:** a clean checkout can launch the pinned Isaac runtime and display a
versioned USD scene on the Mac.

## M1 — First real reef site

- Select one Reefs4D reconstruction and verify its license and checksum.
- Normalize scale, orientation, topology, texture, and level of detail.
- Define WGS84 and local ENU metadata even if the source geolocation is coarse.
- Add semantic classes for substrate and coral observations.
- Produce source, visual, collision, and analysis representations.

**Gate:** the reef can be re-created from its manifest, inspected at correct
scale, and traced back to immutable source data.

## M2 — Environmental replay

- Define observation, analysis, forecast, scenario, and simulation schemas.
- Ingest a synthetic or authorized Spotter-compatible time series.
- Ingest one gridded wind/wave/ocean product.
- Replay time, visualize vectors and uncertainty, and compare forecast with
  observation without conflating them.

**Gate:** selecting a timestamp reconstructs the site's documented
environmental state and provenance.

## M3 — Underwater robotics

- Import and validate one AUV asset.
- Integrate ROS 2 control, transforms, simulation time, and recording.
- Validate buoyancy, drag, currents, thrusters, and energy accounting.
- Add camera, IMU, depth, DVL, and staged sonar models.
- Separate vehicle-visible measurements from evaluation truth.

**Gate:** a recorded mission can be replayed and evaluated against a versioned
site and environmental scenario.

## M4 — Ecological change

- Register repeated reef reconstructions.
- Represent coral colonies and annotations across time.
- Quantify geometric and semantic change with uncertainty.
- Connect heat stress, visibility, and other environmental covariates without
  claiming causality prematurely.

**Gate:** a scientist can inspect a documented change between two surveys and
reproduce the underlying calculation.

## M5 — Saudi operational pilot

- Select one Saudi dive or monitoring site with a field partner.
- Establish permission, acquisition, metadata, and data-governance protocols.
- Capture or receive photogrammetry and environmental observations.
- Connect authorized live telemetry and forecast feeds.
- Validate simulated sensors and mission results against field measurements.

**Gate:** the system operates continuously for one real site with explicit
freshness, uncertainty, provenance, and failure-state reporting.
