# The Coral City mark

`coral-city.svg` is the source. Everything else is rendered from it, so there is
one drawing and not several that drift apart.

A coral, growing from the floor, and one warm mark above it in the water. The
coral is the place, which is ours and which we keep; the warm mark is the
vehicle, which is yours and which you bring. That is the whole product in two
shapes, and it was worth choosing them that way round.

It is a silhouette because it has to survive being sixteen pixels wide — in a
dock, in a browser tab, in a window title. Anything with a horizon or a hull in
it stops being legible somewhere around thirty-two.

## Rendering it

    rsvg-convert -w 256 -h 256 brand/coral-city.svg -o brand/coral-city-256.png

The rendered files are committed rather than generated during a build, so that
building the runtime image does not need a drawing toolchain in it.

| where | what it is |
| --- | --- |
| `services/sim-runtime/apps/coral_city.png` | the application's window icon |
| `apps/console/public/coral-city.svg` | the console's tab icon |

## One thing to know before editing it

The gradient is in `userSpaceOnUse`, deliberately. In the default bounding-box
units a gradient cannot paint a shape whose box has no width, and a perfectly
vertical line has none — so the trunk did not render at all while every branch
that happened to curve did. It also means one gradient across the whole coral
rather than each twig restarting it, which is what makes height read as light.
