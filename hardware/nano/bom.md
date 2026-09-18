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
| WetLink penetrator, M10, sized to the thruster cable | 6 | 13–17 | [penetrators](https://bluerobotics.com/store/cables-connectors/penetrators/wlp-vp/) |
| WetLink penetrator, M10, for the tether | 1 | 13–17 | same |
| Pressure relief / vent plug, M10 | 1 | ~15 | Blue Robotics; **use the 7th hole for this, not the tether, until the tether exists** |

Seven holes, eight things that want one: six thrusters, a tether, a vent
plug. Under a tether the vent plug is the one to give up, and when the tether
comes off, the plug goes in. The rear cap could also be the 4-hole version
with the ESCs potted outside the tube; that is the 2-inch trick and is not
this design.

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
| Pressure and depth sensor, MS5837-02BA (Blue Robotics Bar02 or a breakout) | 1 | 15–85 | mounts in a penetrator hole; **needs one of the seven** |
| 18650 cells, 3S in a holder with a BMS | 3 + 1 | ~25 (est.) | local; do not ship |
| PWM driver, PCA9685, if the Pi's own PWM is not enough | 1 | ~6 | any |
| Leak sensor, two probes on the floor of the tube | 1 | ~5 | any |
| Wiring, connectors, heat-shrink | | ~20 (est.) | |

The depth sensor takes the seventh hole. That settles the count above: six
thrusters plus depth is seven, the tether shares a thruster penetrator sized
for two cables, and the vent plug waits for the four-hole cap that a later
version earns by potting the ESCs outside.

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
