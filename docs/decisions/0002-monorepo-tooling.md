# ADR-0002: Monorepo tooling

- Status: Accepted
- Date: 2026-08-28

## Context

Coral City is one product containing applications, services, contracts,
workflows, integrations, and deployment definitions. Development must behave
consistently on a Mac, the GPU box, and continuous integration without hiding
language-native tools or forcing every component into a JavaScript build graph.

## Options considered

1. Use language-native commands only and document a long manual setup.
2. Use a JavaScript monorepo orchestrator for every component.
3. Pin developer tools with mise, expose repository tasks through just, use
   pnpm only for TypeScript workspaces, and keep native build systems native.

## Decision

- Keep one Git monorepo. Do not add a generic `projects/` directory.
- Use mise to pin executable toolchains shared by developers and CI.
- Use a root Justfile as the small, readable command interface.
- Use pnpm workspaces for TypeScript applications and packages only.
- Keep Go modules, CMake, Cargo, and upstream scientific build systems visible
  and native inside the components that require them.
- Provide stable root commands for setup, validation, testing, local operation,
  and synchronization.
- Keep large scientific data and generated artifacts outside Git; commit only
  manifests, checksums, schemas, and small test fixtures.
- Synchronize reviewable commits through the existing `tools/gpu` workflow so
  Mac, GitHub, and the GPU checkout converge through Git rather than file copy.

## Consequences

- A contributor learns one small command surface without losing access to the
  underlying tools.
- JavaScript tooling cannot become an implicit owner of Go, C++, Rust, or
  scientific builds.
- Root tasks must remain thin wrappers and show the command they invoke.
- Reproducibility depends on maintaining the pinned versions and lockfiles.
- Components may add specialized tools only with documented setup and checks.
