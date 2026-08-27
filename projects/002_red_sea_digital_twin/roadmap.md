# Roadmap and gates

This summary follows the canonical program content in
`website/app/plan-data.ts`. Progress is gate-based: calendar estimates are
planning aids, not acceptance criteria.

## M0–M1 — Foundation and first measured reef — complete

Establish the clean repository and Mac/GitHub/GPU workflow, pin Isaac Sim,
preserve scientific source lineage, and compose the first measured Reefs4D
asset at valid scale.

**Gate:** the measured reef composes with valid scale, texture, material,
cameras, checksums, and provenance.

## M2 — Coral District 01 — active, weeks 1–6

Build the first credible 50 × 50 metre robotics district with explicit truth
classes, a measured anchor reef, synthetic context, underwater atmosphere,
useful camera views, and a controllable robot proxy.

**Gate:** a person can enter the district, understand scale and truth, drive a
vehicle, and see a credible reef rather than a test tank.

## M3 — Robot and sensor laboratory — months 2–4

Create one validated BlueROV-class vehicle with marine dynamics, energy,
camera, IMU, depth, DVL, sonar, altimeter, CTD, manual control, ROS 2, and
record/replay.

**Gate:** depth, heading, velocity, and sensor-reference tests pass with
documented tolerances.

## M4 — Ocean data engine — months 4–7

Connect Spotter-compatible and public environmental data; define the shared
model-adapter lifecycle and Environment Package; adopt the first lightweight
wave, circulation, or drift engines; store fields in NetCDF/Zarr; and replay
versioned forcing deterministically.

**Gate:** a selected date produces a traceable reef forcing package and the
same package replays deterministically.

## M5 — Autonomy proving ground — months 6–10

Build standard coverage, inspection, mapping, adaptive-sampling, and fault
missions with visual-sonar SLAM, safe planning, seeded environmental ensembles,
and comparable scorecards.

**Gate:** two autonomy approaches can be compared fairly across identical
seeded scenarios and uncertainty ensembles.

## M6 — Living ecological twin — months 9–15

Connect repeat reconstructions, coral semantics, environmental histories,
change detection, interventions, data assimilation, and higher-fidelity model
adapters where their scientific value has been demonstrated.

**Gate:** the twin answers what changed, why it may have changed, how certain
we are, and where a robot should observe next.

## M7 — Saudi Red Sea field pilot — months 15–24

Partner on one real site, connect authorized observations and telemetry,
rehearse missions in the twin, execute them in the field, quantify sim-to-real
error, and feed the results back into the system.

**Gate:** a field mission planned and rehearsed in Coral City is executed
safely, replayed, and used to update the twin.
