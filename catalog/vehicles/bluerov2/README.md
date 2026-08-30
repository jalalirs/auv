# BlueROV2

The parameters a simulator integrates to make this behave like a submarine
rather than a box with gravity switched off.

## Where these numbers come from

They are **published values for the BlueROV2**, not measurements we took. The
mass, displaced volume, inertia, added mass and drag coefficients are those
commonly cited for the vehicle in the underwater-robotics literature and in the
open BlueROV2 simulation packages; the thruster geometry is the standard
six-thruster vectored layout, and the T200 force figures are the manufacturer's
at 16 V.

That provenance matters. A dive flown on these will behave plausibly, and
plausibly is not the same as correctly: nobody here has put this hull in a tank
and measured its drag. Before any result from this vehicle is used to make a
decision about a real vehicle, these should be checked against a source that
measured them, and the version republished — which is what versions are for.

## Why the two centres differ

The centre of buoyancy sits 2 cm above the centre of gravity. That separation is
the lever arm that rights the vehicle when it rolls; a model that lets the two
coincide has no restoring moment at all and will hold any attitude it is pushed
into. The platform refuses to record dynamics where they coincide, because that
failure is silent rather than loud.

## What is missing

No hull collision mesh yet — the package carries the visual USD only. Until
there is one, contact with the world is approximated, and a survey that depends
on getting close to structure will not be trustworthy.
