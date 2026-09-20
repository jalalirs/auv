# Mini ROV: what to buy, Amazon.sa

Prices as shown on 20 September 2026, delivering to Riyadh. The vehicle: a
tethered, four-thruster ROV for the tank, brain on the surface (the DGX
Spark), power down the tether, no battery. One sealed box, four thrusters on
a printed frame, camera behind a clear lid.

## Already owned from the 19 September order

Pi Zero 2 W · Camera Module 3 Wide · 22-pin camera cable · micro-USB
Ethernet adapter · BNO055 · LM2596 buck · 12 V 5 A supply · round Cat6
15 m · PG7 glands · 3 kg / 0.1 g scale · wheel weights · ESP32 · breadboard
kit. All of it is used here. The gear motor, BTS7960, silicone and steel
wire are shelved for the fish.

## To buy

| # | Item | Pick | Qty | SAR each | Search on Amazon.sa | Why this one |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Thrusters | **Cryfokt Underwater Thruster 500KV, 60 mm propeller**, two "Forward" (CW) and two "reverse" (CCW) | 4 | 185–191 | `Cryfokt Underwater Thruster 500KV 60mm` | A 2838 outrunner in a duct, about 2 kg of thrust at 12 V, 300 m rated, the standard hobby ROV unit. Ships from outside KSA, arrives about 5 October. Bare motor, no ESC |
| 2 | ESCs | **Readytosky Bidirectional ESC 20 A, 2-4S, with 5 V UBEC, pack of 4** | 1 | 213 | `Readytosky Bidirectional ESC 20A` | Reverse is built into the firmware, so no flashing. 20 A per thruster is the tank limit we run at, not the motor's ceiling. The UBEC gives 5 V for the PWM board |
| 3 | PWM board | **DollaTek PCA9685 16-channel PWM driver** | 1 | 27 | `PCA9685 16 channel PWM servo driver` | The Pi Zero has two hardware PWM pins and we need four clean 50 Hz signals. I²C, same bus as the BNO055 |
| 4 | Dry box | **LeMotech ABS junction box 200 × 120 × 75 mm, IP65, clear polycarbonate cover** | 1 | 99 | `ABS junction box transparent cover 200x120x75 IP67` | The hull. Pi, PCA9685, four ESCs, buck and IMU fit on a printed tray inside; the camera looks through the clear lid. IP65 is splash, not depth: the lid gasket gets a smear of silicone grease and the box is tested at 1 m first. Amazon Germany stock, about 27 September |
| 5 | Surface power | **12 V 20 A 240 W switching supply**, the 82 SAR generic | 1 | 82 | `12V 20A 240W switching power supply` | Four thrusters at half throttle draw more than the 5 A brick we have. That brick stays for bench work on one thruster |
| 6 | Tether power | 2 × 2.5 mm² flexible cable, 15 m | 1 | ~60 | any electrical shop or SACO; Amazon.sa only has speaker cable at 173 | 2.5 mm² keeps the drop under 1 V at 10 A over 15 m each way. Taped to the Cat6 every 30 cm |
| 7 | Grease | Mission Automotive dielectric silicone grease | 1 | 174 | `marine grease silicone grease dielectric tube` | Overpriced here; a 20 g tube from any car parts shop in Riyadh is 15 SAR and enough. Buy locally |
| 8 | Buoyancy | closed-cell foam: a pool noodle or a yoga block | 1 | ~25 | SACO or any sports shop | The box is the only air; four thrusters sink it. Foam strapped to the top rails brings it back |
| 9 | Printing | frame and tray in PETG at Sketchat | 1 set | ~200 | sketchat.sa | Two side rails that clamp the box, four thruster saddles, the inside tray |

Amazon.sa total: about **1,180 SAR** (thrusters 750, ESCs 213, board 27,
box 99, supply 82). Local: about 300. With what is already owned the whole
vehicle is about 2,900 SAR.

## What the thruster listing must say before you add it

Open the Cryfokt listing and check: 2838 or F2838 motor, 500 KV, 12 to 24 V,
60 mm propeller, three wires out. Buy two of the "Forward" listing and two of
the "reverse". If the reverse one is out of stock, buy four Forward; a
reversed propeller only matters for cancelling torque, and the ESCs run
either direction.

## Layout

Two vertical thrusters on the box's centreline, fore and aft, for depth and
pitch. Two horizontal at the rear corners, for drive and yaw. No sideways
motion; the BlueROV2's vectored layout comes in version two with six.
