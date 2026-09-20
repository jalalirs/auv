# Mini Titan: what to buy

Prices as shown on Amazon.sa, 20 September 2026, delivering to Riyadh.

## Already owned or in today's cart

From 19 September: Pi Zero 2 W · Camera Module 3 Wide · 22-pin camera cable
· micro-USB Ethernet adapter · BNO055 · LM2596 buck · round Cat6 15 m · PG7
glands · scale · wheel weights · ESP32 · breadboard kit.

From today's cart: 4 × Cryfokt thruster · Readytosky 20 A bidirectional
ESC, pack of 4 · PCA9685. Two changes to make in the cart:

- **The box: change the size to 6.2" × 3.5" × 2.3"** (158 × 89 × 58 mm),
  same LeMotech clear-cover listing, about 45 SAR. The 200 × 120 × 75 made
  the capsule either too wide or too tall; this one gives the Titan's
  proportion.
- **Remove the RUIZHI 12 V 20 A supply.** The single-tether design below
  runs on 48 V and steps down inside.

## To add for the Titan layout

| # | Item | Pick | Qty | SAR | Why |
| --- | --- | --- | --- | --- | --- |
| 1 | Thrusters | Cryfokt 500KV 60 mm, one more Forward and one more reverse | 2 | 376 | six pods: four vertical, two horizontal. Three CW and three CCW so reaction torque cancels |
| 2 | ESCs | Readytosky Bidirectional 20 A, single, with UBEC | 2 | 172 | the 4-pack covers four; singles are 86 each. Or a second 4-pack at 213 and keep two spares |

## The one tether

One round Cat6 carries everything: Ethernet on two pairs, 48 V on the other
two, into one PG9 gland in the box's top wall under the cover's connector
dome. The vehicle boots when it is plugged in. Nothing else crosses the skin.

| # | Item | Pick | Qty | SAR | Search on Amazon.sa | Why |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | Surface supply | 48 V 5 A 240 W switching supply, open frame | 1 | ~110 | `48V 5A 240W switching power supply` | 3 A at 48 V is 150 W at the vehicle; over 15 m of Cat6 the drop is about 4 V |
| 4 | Converter | DC-DC 48 V to 12 V 20 A 240 W step-down, sealed | 1 | ~70 | `48V to 12V 20A 240W DC DC converter` | inside the box, feeds the ESCs; the LM2596 then makes 5 V for the Pi |
| 5 | Gland | PG9 nylon cable gland, IP68, 4–8 mm | 1 pack | ~15 | `PG9 cable gland waterproof` | the round Cat6 is 6–7 mm; the owned PG7 stops at 6.5 |
| 6 | RJ45 splitter | passive PoE injector/splitter pair, 5.5 mm barrel | 1 | ~25 | `passive PoE injector splitter` | puts 48 V on pins 4-5 and 7-8 at the surface and takes it off in the box without cutting the cable |

About **770 SAR** on top of today's cart, less the 110 for the 12 V supply
if it comes out. The 2 × 2.5 mm² power flex is no longer needed.

## Order at JLC3DP on day one

Upload these three STEP files from `hardware/out/titan/`, material **MJF
PA12 (nylon)**, finish as-printed. Nothing on them depends on a measurement.

| File | Colour | Size, mm |
| --- | --- | --- |
| `cover.step` | dyed orange if the site offers it for PA12, else grey and spray-painted | 275 × 100 × 57 |
| `chassis.step` | black | 333 × 148 × 67 |
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

- a 30 mm disc of 3 mm clear acrylic, or a small sheet to cut one
- a 26 × 2 mm O-ring, or a strip of 2 mm silicone cord
- a small tube of silicone grease for the box gasket
- silicone sealant, M3 screws, four M3 brass inserts for the cover, two 25 mm webbing straps
