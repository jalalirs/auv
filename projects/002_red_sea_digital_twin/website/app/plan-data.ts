import releases from "../../program/releases.json";

export type Status = "complete" | "active" | "planned";

export type RoadmapPhase = {
  id: string;
  number: string;
  title: string;
  horizon: string;
  status: Status;
  intent: string;
  outcome: string;
  deliverables: string[];
  acceptanceTests: string[];
  gate: string;
};

export const program = {
  name: "Coral City",
  subtitle: "Red Sea robotic digital twin laboratory",
  version: "Program blueprint 1.2",
  updated: "27 August 2026",
  horizon: "24-month field pilot",
  currentGate: "R1 · Scientific Reef Atlas",
  northStar:
    "A living, uncertainty-aware reef twin where real observations become explorable 3D state, ocean predictions become environmental forcing, and autonomous vehicles can be trained, challenged, compared, and deployed safely.",
};

export const truthClasses = [
  { id: "observed", label: "Observed", detail: "Direct field measurement or survey" },
  { id: "derived", label: "Derived", detail: "Processed from observations" },
  { id: "assimilated", label: "Assimilated", detail: "Model constrained by observations" },
  { id: "forecast", label: "Forecast", detail: "Predicted state with uncertainty" },
  { id: "synthetic", label: "Synthetic", detail: "Designed training content" },
  { id: "experimental", label: "Experimental", detail: "Hypothesis or intervention" },
];

export const architecture = [
  {
    id: "observe",
    number: "01",
    label: "Observe",
    title: "Field and remote sensing",
    summary: "Collect the physical, geometric, chemical, and biological evidence that anchors the twin.",
    inputs: ["AUV / ROV video", "Spotter and moorings", "ADCP, CTD, sonar", "Satellite and weather"],
    output: "Timestamped, calibrated observations with provenance and quality flags",
  },
  {
    id: "reconstruct",
    number: "02",
    label: "Reconstruct",
    title: "Reef geometry factory",
    summary: "Turn video and survey imagery into scaled, georegistered, semantic 3D reef state.",
    inputs: ["Camera calibration", "SfM + MVS", "Meshes / splats", "Semantic segmentation"],
    output: "Tiled OpenUSD reef observations with LODs, labels, uncertainty, and lineage",
  },
  {
    id: "assimilate",
    number: "03",
    label: "Assimilate",
    title: "Ocean and ecosystem state",
    summary: "Fuse observations with weather, waves, circulation, and ecological models instead of showing disconnected feeds.",
    inputs: ["Forecast ensembles", "Wave spectra", "Water-column sensors", "Reef health surveys"],
    output: "A time-indexed best estimate of reef conditions and confidence",
  },
  {
    id: "simulate",
    number: "04",
    label: "Simulate",
    title: "Federated simulation lab",
    summary: "Use each simulator for what it does best behind one scenario and ROS 2 contract.",
    inputs: ["Isaac Sim", "Stonefish / DAVE", "Coastal model fields", "Deterministic scenarios"],
    output: "Repeatable worlds, realistic sensors, marine dynamics, and controlled failures",
  },
  {
    id: "autonomy",
    number: "05",
    label: "Autonomy",
    title: "Robot intelligence",
    summary: "Develop perception, localization, planning, control, and multi-vehicle coordination against measurable missions.",
    inputs: ["ROS 2 Jazzy", "SLAM and mapping", "Mission planning", "Learning policies"],
    output: "Versioned autonomy stacks with comparable performance and safety evidence",
  },
  {
    id: "operate",
    number: "06",
    label: "Operate",
    title: "Mission control and learning loop",
    summary: "Rehearse, deploy, monitor, replay, and feed field outcomes back into the twin.",
    inputs: ["SIL / HIL", "AUV missions", "Operator decisions", "Field results"],
    output: "Safer deployments, fresh observations, and continuously calibrated models",
  },
];

export const reconstructionSteps = [
  ["Capture", "Calibrated overlapping video, navigation, depth, time, and environmental metadata"],
  ["Quality control", "Blur, visibility, coverage, scale, clock alignment, and calibration checks"],
  ["Recover geometry", "Structure-from-motion, dense reconstruction, mesh or Gaussian representation"],
  ["Make scientific", "Scale, local frame, georegistration, uncertainty, provenance, and immutable source"],
  ["Understand", "Coral, substrate, algae, damage, nursery, and habitat semantic layers"],
  ["Publish to twin", "OpenUSD tiles, LODs, collision proxies, sensor materials, and time version"],
  ["Detect change", "Align repeat surveys and quantify growth, loss, bleaching, breakage, and error"],
];

export const simulationLayers = [
  {
    title: "Experience and operations",
    body: "Mission Control, dive views, science overlays, forecast playback, experiment comparison, and replay.",
    tech: "Web control room · Isaac viewport · reports",
  },
  {
    title: "Autonomy contract",
    body: "One ROS 2 interface for simulated vehicles, software-in-the-loop, hardware-in-the-loop, and field robots.",
    tech: "ROS 2 Jazzy · bags · scenario API",
  },
  {
    title: "Simulator federation",
    body: "Photorealism and synthetic sensing in Isaac; marine-dynamics reference tests in Stonefish or DAVE; external ocean fields as forcing.",
    tech: "OpenUSD · PhysX · acoustic models · marine force plug-ins",
  },
  {
    title: "Living twin state",
    body: "Spatial tiles, observations, environmental fields, ecological state, assets, missions, lineage, and uncertainty through time.",
    tech: "STAC-like catalog · Zarr / NetCDF · Parquet · object storage",
  },
  {
    title: "Models and data assimilation",
    body: "Regional forecasts downscaled into coastal and reef conditions, constrained by satellites, Spotters, moorings, and robot measurements.",
    tech: "WRF / public NWP · MITgcm-class ocean · waves · ensembles",
  },
  {
    title: "Field observatory",
    body: "AUVs, ROVs, gliders, Spotters, smart moorings, ADCPs, CTDs, fixed cameras, and repeat photogrammetry.",
    tech: "Real Red Sea evidence",
  },
];

export const growthAreas = [
  ["Assets", "Measured and synthetic 3D sources, manifests, scale, licences, and lineage."],
  ["Pipelines", "Photogrammetry, semantic processing, tiling, change detection, and data preparation."],
  ["Model adapters", "Independent wrappers for weather, waves, circulation, drift, sediment, and ecology."],
  ["Services", "Catalog, time-aware twin state, orchestration, storage, and stable APIs."],
  ["Simulation", "Thin Isaac and reference-simulator integrations that consume canonical packages."],
  ["Robotics", "ROS 2 vehicles, sensors, autonomy, mission control, recording, and evaluation."],
  ["Scenarios", "Immutable experiment manifests connecting a site, time, model run, robot, and mission."],
  ["Experience", "The blueprint, scientific explorer, operational dashboard, and reports."],
] as const;

export const modelRegistry = [
  { name: "OpenDrift", family: "Drift", purpose: "Oil, objects, larvae, plumes, SAR", licence: "GPLv2", build: "pip · Python", phase: "M4" },
  { name: "SWAN", family: "Waves", purpose: "Nearshore wave transformation", licence: "GPL", build: "Makefile", phase: "M4" },
  { name: "HYSPLIT", family: "Atmosphere", purpose: "Dust and pollution trajectories", licence: "Terms apply", build: "Binaries", phase: "M6" },
  { name: "WAVEWATCH III", family: "Waves", purpose: "Basin and regional wave boundary", licence: "NOAA open", build: "CMake", phase: "M4" },
  { name: "SCHISM", family: "Coastal ocean", purpose: "Circulation, water level, surge", licence: "Apache 2.0", build: "CMake · ParMETIS", phase: "M4" },
  { name: "FABM + ERSEM + GOTM", family: "Ecology", purpose: "Mixing, nutrients, oxygen, plankton", licence: "Verify bundle", build: "CMake", phase: "M6" },
  { name: "MITgcm", family: "Ocean", purpose: "Regional circulation experiments", licence: "MIT", build: "genmake2", phase: "M6" },
  { name: "ADCIRC", family: "Coastal ocean", purpose: "Tides, water levels, storm surge", licence: "Registration", build: "CMake", phase: "M6" },
  { name: "WRF + WPS", family: "Weather", purpose: "High-resolution atmospheric forcing", licence: "Public domain*", build: "Complex", phase: "M6" },
  { name: "Delft3D", family: "Coastal ocean", purpose: "Flow, sediment, morphology, turbidity", licence: "Verify modules", build: "Autotools", phase: "M6" },
] as const;

export const environmentPackage = [
  "Site, grid, and vertical datum",
  "Issue time, valid time, and ensemble",
  "Variables, units, and uncertainty",
  "Truth class and interpolation policy",
  "Inputs, executable, configuration, and checksums",
] as const;

export const roadmap = releases as RoadmapPhase[];

export const missionCatalog = [
  ["Coverage survey", "Map a bounded district with minimum energy and complete overlap."],
  ["Reef-safe inspection", "Maintain stand-off distance while resolving colony-scale detail."],
  ["Visual–sonar SLAM", "Stay localized through turbidity, shadows, and repetitive structure."],
  ["Adaptive sampling", "Choose the next measurement that most reduces scientific uncertainty."],
  ["Change response", "Revisit suspected breakage, bleaching, disease, or sediment deposition."],
  ["Plume tracking", "Follow a temperature, turbidity, nutrient, or pollutant feature."],
  ["Multi-vehicle survey", "Coordinate coverage and communication across a small fleet."],
  ["Field rehearsal", "Run the actual mission plan in SIL and HIL before entering the water."],
];

export const scorecards = [
  ["Scientific fidelity", "Scale and registration error · reconstruction completeness · sensor bias · forecast skill · uncertainty calibration"],
  ["Robot performance", "Mission success · localization error · reef contact · coverage · energy · information gain"],
  ["Simulation quality", "Determinism · real-time factor · sensor timing · cross-simulator agreement · domain coverage"],
  ["Operational trust", "Data freshness · lineage completeness · uptime · replayability · safe field transfer"],
];

export const budget = [
  ["Software, twin, robotics", 650],
  ["Surveys and reef data", 250],
  ["AUV / ROV platforms", 400],
  ["Ocean observing sensors", 300],
  ["Compute and storage", 150],
  ["Field validation", 150],
  ["Contingency", 100],
] as const;

export const principles = [
  ["Evidence before spectacle", "A beautiful world is useful only when measured, derived, forecast, and synthetic content remain distinguishable."],
  ["Federate, do not lock in", "Isaac is the primary experience and robotics kernel, while stable contracts allow specialist simulators and ocean models to participate."],
  ["Uncertainty is a product", "Every state estimate and forecast carries confidence, provenance, and known limitations."],
  ["The same mission everywhere", "Scenario, ROS 2, time, frames, and measurements remain consistent from simulation through hardware and field deployment."],
  ["Reproducibility is acceptance", "A milestone closes only with versioned inputs, deterministic execution, objective checks, and preserved evidence."],
];
