# Client

The client the web application uses to talk to the platform.

Its types are **generated** from `packages/contracts/v1/openapi.yaml`. Nothing
here is written by hand except the thin transport in `src/index.ts`, because a
hand-written client drifts from the API silently and a generated one cannot
(ADR-0009).

```bash
just contracts   # regenerate after changing the contract
```

`src/schema.d.ts` is generated and checked in, so a build does not depend on
running a generator; the check script fails if it is out of date.
