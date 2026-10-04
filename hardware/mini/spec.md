# Coral Mini: the spec

Designed for the simulator first, then built. Not bound to what one shop
stocks: every part is from a maker who ships worldwide (Blue Robotics,
ApisQueen, Raspberry Pi, NVIDIA, JLC3DP, AliExpress). Each number says where
it comes from: **datasheet**, **chosen** (a design decision), or **assumed**
(a guess the sim uses until a part is measured).

## What it is for

A tank vehicle you can write controllers for. Small enough to fly in a
1 × 1 × 1 m tank, fully actuated so a controller can hold station against
a current, and built on the stack real ROVs use so what works in the tank
works in the sea.

## The split: body in the water, brain on the network

| | Where | Does |
|---|---|---|
| **Body** | inside the vehicle | sensors, thrusters, attitude and depth hold at 400 Hz, surfaces by itself if the tether goes quiet |
| **Brain** | DGX Spark, on the home network | vision, autonomy, your iocean controller at 20–50 Hz over the tether, and training in the simulator |

The tether runs to a small switch beside the tank and from there to the
DGX on a cable (not Wi-Fi), about a millisecond each way. If the link is
slow or lost, the body's own loop keeps it level, at depth, and surfaces it.

The topics between body and brain are iocean's SDK contract, so a
controller flown in the simulator runs on the DGX unchanged.

## The vehicle

| | Pick | Source |
|---|---|---|
| Size | about 300 × 260 × 110 mm | chosen: 3.3 body lengths of tank |
| Mass | about 1.8 kg in air, neutral in fresh water, trimmed with lead | assumed until weighed |
| Shape | the moulded Titan form: red lid, black chassis, four wing pods | chosen |
| Dry hull | Blue Robotics 3" locking acrylic tube, 200 mm, aluminium rear cap | datasheet: 76.2 ID, 88.9 OD |
| Nose | 3" acrylic dome, camera tilts behind it | datasheet |
| Thrusters | 8 × ApisQueen UG500, 36 mm prop, about 4 N each | datasheet: 4 N, 18 g motor |
| Layout | 4 vertical in the wing pods; 4 horizontal at the hull's corners at 45°, the BlueROV2 Heavy layout | chosen: moves sideways, which a Titan cannot |
| ESCs | 2 × 4-in-1 BLHeli_32, 3D mode, inside the tube | chosen |
| Computer | Raspberry Pi 5, 4 GB | chosen |
| Flight controller | Blue Robotics Navigator on the Pi, ArduSub under BlueOS | datasheet: BlueOS 1.4+ runs Navigator on a Pi 5 |
| IMU, compass, barometer | on the Navigator | datasheet |
| Depth | Blue Robotics Bar02, 0.16 mm resolution | datasheet |
| Camera | Blue Robotics Low-Light HD USB, 1080p30, encodes H.264 itself (the Pi 5 cannot) | datasheet |
| Camera tilt | servo, ±45° | chosen |
| Lights | 2 × small LED, 500 lm, in the front pods' noses | assumed |
| Leak | SOS leak probes at both ends of the tube | datasheet |
| Battery | 4S1P 21700 Li-ion (Molicel P42A), 4.2 Ah, 60 Wh, inside the tube | datasheet |
| Runtime | about 2 h at 25 W | derived: Pi + Navigator 8 W, camera 2 W, thrusters 15 W average |
| Penetrators | WetLink, one per pod (vertical and horizontal thruster share a 6-core cable), tether, depth, lights | chosen |
| Tether | 10 m neutrally buoyant, 2 twisted pairs, plain 100 Mb Ethernet, data only | chosen: the battery powers it |

## The tank rig

| | Pick |
|---|---|
| Tank | 1 × 1 × 1 m, 12 mm glass, on a steel stand 0.6 m high |
| Floor | sand, rock, a few corals, a school of small fish |
| Overhead camera | a PoE network camera 1.2 m above the water, on the same switch, tracking an AprilTag on the lid; this is the tank's "GPS" |
| Wind | a fan over the surface, 0–5 m/s: ripples, moving light on the floor, a surface drift |
| Current | a circulation pump, 0–0.15 m/s |
| Light | an LED panel over the tank |
| Beside the tank | a small PoE gigabit switch: the tether, the overhead camera, and one cable to the DGX |

## In the simulator

The same parts as numbers: mass and inertia from the model, buoyancy from
displaced volume, eight thrusters with their curve, camera field of view
and noise, IMU and depth noise from datasheets, tether drag. Views: the
room outside the tank, the ROV's camera, overhead, front, side, chase.
