# The contract, and the two ways it is spoken

`schema.d.ts` is generated from `packages/contracts/v1/openapi.yaml`. It is the
single description of the platform's API, and nothing else describes it: a route
that is removed or renamed stops compiling wherever it is used rather than
failing at run time.

There are two clients over it, and they are different on purpose.

The console runs in a browser on the platform's own origin, so its session is a
cookie that script cannot read. That is a real property worth keeping, and it is
why the console's client sends no token and stores none.

The desktop application runs on somebody's laptop and talks to a box across a
network, so it holds a token and sends it. It cannot use a cookie on an origin
it is not served from.

Same contract, different transports. What must never fork is this file.
