# Seaglider

A buoyancy glider: 52 kg, 1.8 m, a thousand metres, ten months. No propeller
anywhere on it. It sinks and rises by changing its volume, and its wings turn
that into glide; it steers by shifting and rolling its battery.

## Where these numbers come from

Eriksen et al., *Seaglider: a long-range autonomous underwater vehicle for
oceanographic research* (IEEE JOE, 2001): the wing model, the hull's
compressibility, the mass shifter. See `dynamics.json`, where each number says
where it came from.

## The hull

`seaglider.usd` is drawn by `hardware/seaglider/shape.py` (4 October 2026): 1.8 m
of fairing, about a metre of wing, a rudder above and below the tail, and the
antenna mast it surfaces tail-up to send through. The fairing's width and the
wing's planform are read off photographs, not published. `picture.jpg` is a
render of it.

## Why it cannot be flown yet

The platform flies vehicles by allocating thrust to thrusters, and this one
has none. It becomes flyable when the runtime flies a glider: buoyancy, the
mass shifter and the wings as its actuators.
