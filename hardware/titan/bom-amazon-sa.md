# Mini Titan: what to buy

The vehicle is half the Titan: 222 × 205 × 87 mm, under a kilo. That size
comes from two choices, the smallest box a Pi fits in and the smallest real
thruster, and everything else follows.

## Already owned, from 19 September

Pi Zero 2 W · Camera Module 3 Wide · 22-pin camera cable · micro-USB
Ethernet adapter · BNO055 · LM2596 buck · round Cat6 15 m · PG7 glands ·
scale · wheel weights · ESP32 · breadboard kit. All used.

## What to change in the cart

The 20 September cart was for the big version. Swap these:

| Remove | Replace with | Qty | SAR | Where |
| --- | --- | --- | --- | --- |
| 4 × Cryfokt 2838 thruster | **ApisQueen UG500**, 3 × CW + 3 × CCW | 6 | ~90 each | Amazon.sa search `ApisQueen UG500`; or [underwaterthruster.com](https://www.underwaterthruster.com/products/apisqueen-uq500-mini-brushless-thruster-motor-small-size-and-light-weight-perfect-for-small-size-rovs/) at 24 USD, ships to KSA |
| Readytosky 20 A ESC 4-pack | **4-in-1 drone ESC, 30 × 30 mm, 20–35 A, 3–6S, BLHeli_32** | 2 | ~180 each | search `4in1 ESC 35A BLHeli_32 6S`; BLHeli_32 has 3D mode, which is reverse |
| LeMotech 200 × 120 × 75 box | **LeMotech 3.9" × 2.6" × 1.9"**, 100 × 68 × 50, clear cover, single | 1 | 60 | same listing, the size it opened on |
| RUIZHI 12 V 20 A supply | **24 V 5 A 120 W** switching supply | 1 | ~70 | search `24V 5A switching power supply` |
| | passive PoE injector + splitter pair, 5.5 mm barrel | 1 | ~25 | search `passive PoE injector splitter` |
| | PG9 nylon cable glands, IP68, 4–8 mm | 1 pack | ~15 | search `PG9 cable gland waterproof` |
| | PCA9685 PWM board | 1 | 27 | keep it, it is right |

About **1,000 SAR** for the swaps. The 12 V 5 A brick from 19 September
stays for bench work.

## Why 24 volts and no converter

Six UG500 at full throttle draw under 8 A at 12 V. On 24 V that is 4 A,
which drops about 5 V over 15 m of Cat6 on two pairs, so the vehicle sees
19 V. The UG500 is rated to 24 V and the ESCs are 6S, so the thrusters run
straight off the tether and only the Pi needs a step-down, the LM2596
already owned. One cable, one gland, nothing warm in the box.

## Order at JLC3DP on day one

Upload these three STEP files from `hardware/out/titan/`, material **MJF
PA12 (nylon)**. Nothing on them depends on a measurement.

| File | Colour | Size, mm |
| --- | --- | --- |
| `cover.step` | dyed orange if offered for PA12, else grey and painted | 170 × 77 × 45 |
| `chassis.step` | black | 212 × 109 × 50 |
| `bezel.step` | black | 40 × 40 × 4 |

Expect 50 to 90 USD for the set.

## Print later, at Sketchat, after measuring

| File | Waits for |
| --- | --- |
| `pods.step`, six copies | the UG500 guard's outside diameter, 44 assumed |
| `tray.step` | the box's inside and its corner bosses |

## From SACO or any hardware shop

- a 26 mm disc of 3 mm clear acrylic, or a small sheet to cut one
- a 22 × 2 mm O-ring, or a strip of 2 mm silicone cord
- a pool noodle: the buoyancy foam for the nose, the tail, and the two sheets over and under the box
- a small tube of silicone grease for the box gasket
- silicone sealant, M3 screws, four M3 brass inserts for the cover, two 20 mm webbing straps
