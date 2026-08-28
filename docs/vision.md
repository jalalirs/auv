# Vision

## The product story

A scientist opens Coral City and selects a Red Sea reef site. The screen shows
the best available 3D reconstruction of that reef, when it was measured, how it
was produced, where its uncertainty lies, and how it differs from earlier
surveys.

The scientist selects a past date, the present, or a forecast window. Coral
City combines observations, forecasts, and model results without confusing one
for another. Wind, waves, currents, temperature, visibility, and ecological
records become a versioned environmental state around the reef.

An engineer creates an AUV mission against that exact site and environmental
state. Isaac Sim renders the world and sensors. ROS 2 runs the autonomy stack.
The team can rehearse perception, SLAM, planning, control, sampling, and swarm
behaviour under repeatable conditions before risking equipment or habitat.

When the real mission begins, a field edge station retains safety authority and
continues operating if connectivity is lost. After the mission, telemetry,
images, sonar, samples, and operator records return to Coral City. They become
new evidence rather than silently overwriting the previous twin.

## Questions Coral City must answer

1. What was measured at this reef, when, where, by whom, and with what quality?
2. What is happening now, and which values are observations versus estimates?
3. What may happen under a stated forecast or scientific scenario?
4. How has reef geometry or ecological state changed between surveys?
5. Can an autonomous vehicle complete a mission safely under those conditions?
6. What happened during the simulated or real mission, and can it be reproduced?

## Intended users

- Marine scientists and reef ecologists
- Oceanographers and environmental modellers
- Robotics, perception, and autonomy researchers
- Mission planners and field operators
- Data stewards and scientific reviewers
- Partner institutions and, later, public science audiences

## Scale of ambition

The target is a production scientific and robotics platform worthy of a
multi-institution, multi-year programme—not a collection of demos. It begins
with one deeply complete reef site and grows through stable contracts to more
sites, models, vehicles, sensors, and partners.

## Scientific honesty

Photorealism must never imply scientific certainty. Every displayed or computed
value carries an explicit truth class:

- observation;
- analysis or reconstruction;
- forecast;
- scenario input; or
- simulation output.

Unknown coordinates, datums, rights, calibration, and uncertainty remain
visible. A beautiful asset with incomplete evidence is not silently promoted
to operational truth.

## Success

Coral City succeeds when a team can move from evidence to understanding, from
understanding to a repeatable simulated mission, and from the field back to new
evidence—without losing provenance at any boundary.
