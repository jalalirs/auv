# Nano: bill of materials

Prices in USD as listed on 18 September 2026, before shipping and Saudi
customs. Where a price is an estimate it says so. The printed parts are the
three STEP files `model.py` writes to `hardware/out/`.

## The dry hull (Blue Robotics, 3" locking series)

| Part | Qty | Each | Source |
| --- | --- | --- | --- |
| 3" acrylic tube, 150 mm, BR-102649-150 | 1 | 115 | [tube](https://bluerobotics.com/store/watertight-enclosures/locking-series/wte-locking-tube-r1-vp/) |
| 3" locking flange with O-rings | 2 | 34 (from) | [flanges](https://bluerobotics.com/store/watertight-enclosures/locking-series/wte-locking-tube-r1-vp/) |
| 3" acrylic end cap, blank (the window) | 1 | 16 | [end caps](https://bluerobotics.com/store/watertight-enclosures/locking-series/wte-end-cap-vp/) |
| 3" aluminium end cap, 7 × M10 | 1 | 32 | same |
| Potted penetrator, M10, blank, epoxy-filled: two thruster cables each | 3 | ~6 | [potted penetrators](https://bluerobotics.com/store/cables-connectors/penetrators/penetrator-vp/) |
| WetLink penetrator, M10, for the tether | 1 | 13–17 | [penetrators](https://bluerobotics.com/store/cables-connectors/penetrators/wlp-vp/) |
| Pressure relief / vent plug, M10 | 1 | ~15 | Blue Robotics |

**The seven holes.** Six thruster cables, a depth sensor, a tether and a vent
plug want nine, and the cap has seven. The UG500's cable is thin, so two of
them go through one epoxy-potted penetrator: three for the thrusters, one
for the depth sensor, one for the tether, one for the vent plug, one spare
for the leak sensor's future or a second camera. A WetLink takes one cable
only, which is why the thruster holes are potted and the tether's is not.

## Propulsion

| Part | Qty | Each | Source |
| --- | --- | --- | --- |
| ApisQueen UG500, 3 × CW + 3 × CCW | 6 | 23.91 | [UG500](https://www.underwaterthruster.com/products/apisqueen-uq500-mini-brushless-thruster-motor-small-size-and-light-weight-perfect-for-small-size-rovs/) |
| 4-in-1 brushless ESC, 20 A, BLHeli_S, bidirectional firmware | 2 | ~25 (est.) | any drone shop; **must be flashed for reverse** |

Opposite-handed pairs cancel each other's reaction torque: CW and CCW
diagonally on the verticals, one of each at the stern.

## Inside the tube

| Part | Qty | Each | Source |
| --- | --- | --- | --- |
| Raspberry Pi Zero 2 W | 1 | 15 | official |
| Raspberry Pi Camera Module 3, wide | 1 | 35 | official |
| IMU, BNO085 breakout | 1 | ~25 | Adafruit or clone |
| Pressure and depth sensor, MS5837-02BA (Blue Robotics Bar02 or a breakout) | 1 | 15–85 | mounts in one of the seven holes |
| 18650 cells, 3S in a holder with a BMS | 3 + 1 | ~25 (est.) | local; do not ship |
| PWM driver, PCA9685, if the Pi's own PWM is not enough | 1 | ~6 | any |
| Leak sensor, two probes on the floor of the tube | 1 | ~5 | any |
| Wiring, connectors, heat-shrink | | ~20 (est.) | |

## Outside

| Part | Qty | Each | Source |
| --- | --- | --- | --- |
| Printed: cover, chassis, bezel, MJF PA12 | 1 set | 80–140 (est.) | [JLC3DP](https://jlc3dp.com/3d-printing-quote); upload the three STEP files |
| Dye or paint for the cover, orange | | ~10 | |
| Small 12 V LED lights in 20 mm cans | 2 | ~8 (est.) | any |
| Mild steel bar 140 × 12 × 6 | 2 | ~3 | any |
| Tether, 5 m: CAT5 plus two power cores, or a 4-core with Ethernet over two pairs | 1 | ~20 (est.) | |
| M3 screws, nyloc nuts | | ~10 | |

## Total

Roughly **850–1,000 USD**, of which the hull is a third and the thrusters a
sixth. Blue Robotics ships to Saudi Arabia by DHL; JLC3DP and ApisQueen too.
Cells are bought locally.

## What to order first

The tube, the flanges, the caps and one UG500. Everything printed is designed
around their real dimensions, and the model's two guesses, `CAP_REACH` and
`THRUSTER_MOTOR_D`, get measured the day they arrive.
