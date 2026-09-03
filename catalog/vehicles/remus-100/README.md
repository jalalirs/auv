# REMUS 100

A torpedo-shaped survey AUV: 1.33 m long, 0.19 m in diameter, one propeller and
four control fins. The vehicle a great deal of the underwater-vehicle control
literature is written against, because its parameters were published in full.

## Where these numbers come from

Timothy Prestero, *Verification of a Six-Degree of Freedom Simulation Model for
the REMUS Autonomous Underwater Vehicle* (MSc thesis, MIT/WHOI, 2001). Mass,
inertia, added mass, cross-flow drag and the centres are his; he measured and
tank-tested them. The propeller thrust is a round figure for the nominal
cruise, not from the thesis.

## Why it cannot be flown yet

This platform allocates thrust across fixed thrusters. A REMUS steers with fins,
whose force depends on the speed of the water over them, and the allocator does
not model control surfaces. The vehicle is catalogued so that its physics can
be read and compared, and it becomes flyable when control surfaces are.

No hull package yet either.
