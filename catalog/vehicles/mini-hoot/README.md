# mini-hoot

iocean's first vehicle: a small, fully actuated ROV for a 1 m tank, in the
moulded Titan form. A Blue Robotics 3" tube is the dry hull and its dome the
nose; eight ApisQueen UG500 thrusters, four vertical in wing pods and four
horizontal toed in at the corners; a Raspberry Pi 5 with a Navigator running
ArduSub inside; 10 m of data-only tether to a DGX Spark that runs the
controllers.

Designed in the simulator first. Nothing here is measured: mass and buoyancy
are summed from the parts, and the hydrodynamic coefficients are the
BlueROV2's scaled to this size. dynamics.json says which number is which.

The drawing, the parts and the build: `hardware/mini/` (spec.md, params.py,
shape.py, package.py).
