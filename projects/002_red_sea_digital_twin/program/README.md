# Coral City release program

`releases.json` is the canonical release roadmap used by the blueprint website.
A release is an independently useful, operated system—not a proof of concept,
technology spike, asset import, or screenshot.

## Release rules

- Every release has a human outcome, complete scope, objective acceptance tests,
  an operational runbook, and preserved evidence.
- Spikes, prototypes, and experiments are tasks inside a release. They never
  count as releases and do not satisfy an acceptance test.
- A release is `active`, `planned`, or `complete`. There are no invented
  completion percentages.
- `complete` means every acceptance test passed against a versioned build and
  the evidence can be reproduced by someone other than the original developer.
- Later releases extend stable contracts. They may replace internal
  implementations without invalidating earlier release behavior.
- Security, data governance, observability, backup, documentation, and operator
  usability are part of each release—not a final cleanup phase.

## Task hierarchy

```text
Release — a usable system with an acceptance gate
└── Capability — a coherent user or scientific ability
    └── Work package — code, data, integration, documentation, or operations
        └── Task — a small reviewable change with its own verification
```

The active work list is maintained in `current-release.md`. Only work required
to pass the active release belongs there.
