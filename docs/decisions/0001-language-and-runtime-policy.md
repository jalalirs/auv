# ADR-0001: Language and runtime policy

- Status: Accepted
- Date: 2026-08-28

## Context

Coral City spans a cloud product, browser visualization, robotics, simulation,
edge operation, and scientific software. One language cannot serve every area
well, but an unconstrained mix would make the product difficult to understand
and operate. Python must not become the default architecture merely because
some scientific and simulator tools require it.

## Options considered

1. Use Python throughout for maximum scientific-library compatibility.
2. Use Rust throughout for one strongly typed systems language.
3. Use a deliberately small set of languages, with each language confined to
   a clear runtime boundary.

## Decision

Use the following language boundaries:

- Go owns the cloud control plane and network services.
- TypeScript owns browser applications and generated web clients.
- C++ owns ROS 2 components and performance-sensitive robotics integration.
- Rust may be introduced for edge or native components only after a separate
  decision demonstrates a concrete safety, portability, or performance need.
- Python is permitted only inside isolated workflows or adapters when an
  upstream simulator, reconstruction package, or scientific model requires it.
  Python does not own core product APIs, domain contracts, or orchestration.
- Native scientific models retain their upstream languages and build systems
  behind versioned container and data contracts.

The first control-plane implementation targets the current stable Go 1.27
line. Browser development targets the Node.js 24 LTS line. Exact reproducible
tool versions are declared at the repository root rather than repeated in every
component.

## Consequences

- Product behavior remains understandable without importing a scientific
  Python environment into every service.
- Runtime boundaries must communicate through explicit versioned contracts.
- Contributors need more than one language only when they cross a component
  boundary.
- Introducing Rust or a new core language requires another accepted ADR.
- Python dependencies must remain local to the workflow or integration that
  needs them and must never leak into root setup.
