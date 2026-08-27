# Scenarios

A scenario selects, but does not duplicate:

- a versioned site and local coordinate frame;
- a timestamp or replay interval;
- environmental observation and forecast products;
- an ocean-state interpretation policy;
- vehicles, sensors, and autonomy versions;
- mission, initial conditions, and random seed; and
- required recordings and acceptance checks.

Scenario manifests must make a run reproducible without embedding provider
credentials or large data files.
