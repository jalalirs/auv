# Release roadmap

Each release answers one question and ships a complete, testable capability.
Experiments and spikes may happen inside a release but never satisfy its gate.

| Release | Outcome | The question it answers |
| --- | --- | --- |
| R0 *(done)* | Engineering foundation | can we build and ship consistently? |
| **R1** *(in progress)* | The World and its First City | can I see a real ocean, enter a real place, and know what I am looking at and who may see it? |
| R2 | The Evidence Loop | how does a survey become a place? |
| R3 | Environmental Depth | what were and will be the conditions here? |
| R4 | The Simulation Hub | will *my* autonomy work here? |
| R5 | Field Missions | can we actually do this at sea? |
| R6 | Operations | can it be relied upon? |

R1 is described in detail, with its checkpoints, gates, acceptance tests, and
its deliberate exclusions, in [`docs/plan/r1.md`](plan/r1.md). That document is
the authority; this table is the shape.

This supersedes the earlier R1–R5 sequence, which presumed identity, storage,
artifacts, provenance, and execution that did not exist. The outcomes and gates
of the later releases are otherwise preserved.

## Release rule

A release closes only when its user-visible outcome and gate pass against a
versioned candidate with preserved evidence. Schedule pressure does not convert
unfinished work into a completed release.
