# BlueROV2 Heavy

The same hull as the BlueROV2 with the heavy configuration kit: two more
vertical thrusters, one at each corner, and the buoyancy to carry them. The
extra pair is what gives the frame roll and pitch authority; the standard frame
has none and rights itself on its own buoyancy alone.

## Where these numbers come from

The added mass, damping and inertia are those identified in Chu-Jou Wu,
*6-DoF Modelling and Control of a Remotely Operated Vehicle* (MSc thesis,
Flinders University, 2018), which fitted a six-degree-of-freedom model to the
heavy configuration and is the set most of the open BlueROV2 simulators carry.
Mass and displaced volume are the manufacturer's for the heavy kit; the thruster
geometry is the manufacturer's frame drawing; the T200 force figures are the
manufacturer's at 16 V.

Two of the linear damping terms — sway and yaw — were not identified separately
in that work and are carried here as small non-zero values so that every axis
is damped. They are the least trustworthy numbers in this file.

## The hull

`bluerov2-heavy.usd` is drawn by `hardware/bluerov2_heavy/shape.py` on 4 October
2026: the standard frame's published 457 × 254 mm side, the electronics and
battery tubes, buoyancy, lamps, and the eight T200s exactly where the thruster
table above puts them, so the drawing, the propellers a dive turns and the
physics agree. `picture.jpg` is a render of it.

The horizontals are drawn at +0.085 m, above the centre of gravity, because
that is what the thruster table says. Whether that is right depends on Wu's
frame — where its origin is and which way its z points — and is not yet
checked against the source: the real vehicle carries its horizontals low, but
its centre of gravity is low too.
