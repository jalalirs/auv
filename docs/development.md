# Development rules

## Before implementation

Every meaningful component begins with a short reviewed proposal covering:

1. the user or system outcome;
2. its repository location;
3. the contract it owns;
4. the components it may call;
5. the components forbidden from calling it directly;
6. technology and alternatives;
7. data written or changed;
8. deployment shape;
9. tests and acceptance evidence; and
10. rollback or replacement strategy.

No framework scaffold or service code is added before this review.

## Toolchain and commands

The root `mise.toml` is the authority for developer tool versions. After mise is
installed, `mise install` prepares the same Go, Node.js, pnpm, and just versions
on Mac, GPU, and CI.

The stable repository commands are:

| Command | Contract |
| --- | --- |
| `just setup` | Install pinned tools and locked dependencies |
| `just check` | Formatting, vetting, types, and that the generated client still matches the contract |
| `just test` | Every component's tests |
| `just run` | Build and start the whole local platform |
| `just e2e` | Check a running deployment end to end |
| `just contracts` | Regenerate the client from the contract |
| `just logs` / `just stop` / `just reset` | Watch, stop, or discard the local platform |
| `just deploy-gpu` | Build for the GPU host, stream, migrate, start, and check |
| `just sync "message"` | Commit and synchronize a reviewed checkpoint |

These commands remain thin wrappers. Component-native commands stay visible in
their own documentation and continuous-integration logs.

## Change size

- Prefer one explainable architectural decision per commit.
- Keep code changes small enough to review line by line.
- Do not combine structure changes, technology adoption, and product behaviour
  in one commit.
- Generated files must be identifiable and reproducible.

## Dependency direction

Applications and integrations depend on stable contracts. Contracts do not
depend on applications, runtimes, cloud providers, or scientific solvers.

```text
apps ─────────────┐
services ─────────┼──> packages/contracts
workers ──────────┘
```

Cross-area imports that bypass an approved contract are prohibited. The web
application's client is generated from the contract, and a conformance test
fails the build if the contract and the routes actually served disagree.

## Data discipline

- Never commit secrets or credentials.
- Never commit large scientific or robotics data.
- Never overwrite an observation or published artifact.
- Keep checksums and manifests beside the code that interprets them.
- Mark truth class, units, coordinate reference, vertical datum, time basis, and
  uncertainty explicitly.

## Definition of done

A change is not done because it runs once. It requires:

- approved design;
- readable implementation;
- automated checks proportional to risk;
- versioned inputs and outputs where relevant;
- preserved evidence;
- documented operation and failure behaviour; and
- synchronization across Mac, GitHub, and GPU.
