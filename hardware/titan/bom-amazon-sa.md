# Mini Titan: what to buy

Prices as shown on Amazon.sa, 20 September 2026, delivering to Riyadh.

## Already owned or in today's cart

From 19 September: Pi Zero 2 W · Camera Module 3 Wide · 22-pin camera cable
· micro-USB Ethernet adapter · BNO055 · LM2596 buck · round Cat6 15 m · PG7
glands · scale · wheel weights · ESP32 · breadboard kit.

From today's cart: 4 × Cryfokt thruster · Readytosky 20 A bidirectional
ESC, pack of 4 · PCA9685 · LeMotech 200 × 120 × 75 box · RUIZHI 12 V 20 A
supply.

## To add for the Titan layout

| # | Item | Pick | Qty | SAR | Why |
| --- | --- | --- | --- | --- | --- |
| 1 | Thrusters | Cryfokt 500KV 60 mm, one more Forward and one more reverse | 2 | 376 | six pods: four vertical, two horizontal. Three CW and three CCW so reaction torque cancels |
| 2 | ESCs | Readytosky Bidirectional 20 A, single, with UBEC | 2 | 172 | the 4-pack covers four; singles are 86 each. Or a second 4-pack at 213 and keep two spares |

About **550 SAR** on top of today's cart.

## Order at JLC3DP on day one

Upload these three STEP files from `hardware/out/titan/`, material **MJF
PA12 (nylon)**, finish as-printed. Nothing on them depends on a measurement.

| File | Colour | Size, mm |
| --- | --- | --- |
| `cover.step` | dyed orange if the site offers it for PA12, else grey and spray-painted | 225 × 131 × 52 |
| `chassis.step` | black | 270 × 147 × 64 |
| `bezel.step` | black | 46 × 46 × 5 |

Expect 80 to 150 USD for the set. Standard build, ships in about a week.

## Print later, at Sketchat, after measuring

| File | Waits for | Why |
| --- | --- | --- |
| `pods.step`, six copies | the thruster duct's outside diameter | each ring clamps the duct; 72 mm is a guess |
| `tray.step` | the box's inside dimensions and corner bosses | it must sit between the bosses and clear the lid |

Both are PETG, cheap, and bolt on: the pods to the chassis on four M3 each,
the tray on its own feet.

## From SACO or any hardware shop

- 15 m of 2 × 2.5 mm² flexible cable for the tether's power
- a 30 mm disc of 3 mm clear acrylic, or a small sheet to cut one
- a 26 × 2 mm O-ring, or a strip of 2 mm silicone cord
- a small tube of silicone grease for the box gasket
- silicone sealant, M3 and M4 screws, four M4 brass inserts, two 25 mm webbing straps
