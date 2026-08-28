# Web application

- **Outcome:** a person can sign in, find the places they may see, read what is
  recorded there, judge whether to believe it, and watch work run.
- **Location:** `apps/web`.
- **Owned contract:** browser presentation and interaction state.
- **May call:** the control plane, through the generated client only.
- **Forbidden direct calls:** object storage, the record, containers, GPU hosts,
  robots, simulators, and scientific solvers. Bytes are reached through
  short-lived URLs the platform issues, never by addressing storage.
- **Deployment:** static assets served by nginx, which proxies the API on the
  same origin so that the session cookie works and no token is exposed to
  script.

## Two rules

**Nothing is shown that the platform has not said.** Empty states are written as
sentences explaining what would be there and why it is not. The map draws the
extents of places and says plainly that no bathymetry, terrain, or coastline
layer is connected, because none is. A basemap invented for appearance would be
the one thing this platform must never do.

**Nothing decorative may imply certainty.** The marks distinguishing a
measurement from a hypothesis are the strongest signals on the page: an
observation is set solid, and a forecast, scenario, or simulation is set apart
from it in border, style, and colour together, so no glance mistakes one for
another and no colour-blind reader is left without the distinction.

## The evidence rail

The screen for one version exists for its rail: truth class, coordinate
reference, vertical datum, extent, the interval it was measured over, the
instrument clock offset where known, uncertainty, rights, attribution, content
digest, and what produced it. A value shown without those is not evidence,
whatever it looks like. An undetermined uncertainty reads "not determined"
rather than being omitted, because omission reads as confidence.

## Refusals

A refusal is often the most informative answer a screen can give, so it is kept
rather than flattened into an error. A hidden refusal reports absence — the
screen says the thing may not exist or may not be yours to know about, and that
the platform does not distinguish the two. A visible one says it exists and
access may be requested.

## Technology

React and TypeScript built by Vite, with no router dependency: the application
has a handful of screens addressed by path, and forty lines cover it. The client
is generated from the contract; hand-written request code is prohibited
([ADR-0009](../../docs/decisions/0009-api-style.md)), because a hand-written one
drifts silently and a generated one cannot.

No 3D engine is adopted yet, and
[ADR-0011](../../docs/decisions/0011-globe-and-3d-client.md) records why: there
is no geometry to render, and a photorealistic empty globe is the most
convincing possible presentation of nothing.
