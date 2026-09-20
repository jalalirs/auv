# Mini Titan

The first vehicle to build: the Geneinno Titan's construction at half scale,
222 × 205 × 87 mm and under a kilo. A domed orange capsule 77 mm wide and 66
tall on a black chassis; six small thrusters in pods on arms; one tether into
a connector dome on the crown and nothing else on the skin. The dry part is
the smallest IP65 box a Pi fits in, 100 × 68 × 50, lying inside the capsule
with foam above, below, ahead and behind it. The capsule floods. The box seals.

- What to buy: [bom-amazon-sa.md](bom-amazon-sa.md)
- The vehicle as code: [params.py](params.py), [titan.py](titan.py), [budget.py](budget.py)
- As a model you can orbit: <https://claude.ai/code/artifact/23a7dfa7-e69e-4d9a-b4c5-d4e82dce79e7>

```bash
hardware/.venv/bin/python hardware/titan/titan.py                 # STEP + STL into hardware/out/titan
hardware/.venv/bin/python hardware/titan/budget.py
RENDER_OUT=hardware/out/titan hardware/.venv/bin/python hardware/nano/render.py iso open rear under
hardware/.venv/bin/python hardware/titan/sheet.py
```

## Measurements, against the Titan

| | Titan (390 × 347 × 165) | Ours | Ratio, ours ÷ Titan |
| --- | --- | --- | --- |
| Capsule width | ~100 | 77 | 0.77 |
| Capsule height | ~90 | 66 | 0.73 |
| Capsule length | ~340 | 172 | 0.51 |
| Overall length, width | 390, 347 | 222, 205 | 0.57, 0.59 |
| Height over the pods | 165 | 87 | 0.53 |
| Mass | 4,400 g | ~925 g | 0.21 |

Half scale overall. The capsule is a little fatter than half because the
Pi Zero is 65 mm long and no box that holds it is narrower than 68. Its
width-to-height is 1.17, the Titan's 1.1, so it reads right.

What set the size: the thruster. The Cryfokt 2838 duct is 72 mm across and
six of them made the vehicle 0.88 of the Titan. The UG500 is 44 and gives
half. Thrust drops from 15 N to 4 N per unit, which is plenty for a tank and
the reason this one is under a kilo.

## Why this shape

The Titan is three things: a capsule, a chassis with four arms, and six
thrusters in pods. Ours is the same three, and the part that keeps water out
is a bought box inside the capsule rather than a printed shell, because a
print does not seal and a box does. The box is never seen: the capsule's
nose shows only the window bezel and its stern only the two glands.

| Part | What it is | Seals by |
| --- | --- | --- |
| **cover** | orange, the domed upper half of the capsule; three vents, the connector dome; four M4 to the chassis | wet |
| **chassis** | black: the lower half of the capsule, a base plate, four arms to the wing pods, two struts to the stern pods, two cradle ribs the box sits on, ballast rails | wet |
| **box** | LeMotech 100 × 68 × 50 (the 3.9 × 2.6 × 1.9 in size), IP65, lying flat, lid up, held by two ribs in the chassis | its own gasket, greased |
| **window** | 26 mm acrylic in the box's front wall, printed bezel seen through the capsule's nose | O-ring, silicone |
| **the one tether** | round Cat6, Ethernet on two pairs and 24 V on the other two, into one PG9 through the box's lid under the cover's dome | the gland |
| **foam** | closed-cell, cut from a pool noodle: a sheet above the lid, a sheet under the floor, blocks in the nose and the tail | wet; it is what floats the six thrusters |
| **tray** | inside the box: two decks on standoffs, the two 4-in-1 ESCs and the buck below, the Pi, PCA9685 and IMU above | dry |

Six thrusters, the Titan's layout: four vertical in the wings give heave,
roll and pitch; two horizontal at the stern give surge and yaw. Two 4-in-1
drone ESCs drive all six from two 30 mm boards, which is what lets the
small box work.

## The open questions, in the order they close

1. **24 V on Cat6.** Passive PoE at 24 V and 4 A is inside the cable's
   rating; the RJ45 plug at the surface end is fine, and the box end is
   soldered. The ESCs must be 6S-rated and flashed for 3D mode; a 4S board
   here fails on the first plug-in.
2. **The guard.** The Cryfokt listing gives no outside diameter. Every pod is
   a band clamp sized from `DUCT_OD`, 72 in the model; measured on arrival.
3. **The box's wall, lid and corner bosses.** Measured on arrival; the tray
   and the cradle ribs follow.
4. **Trim.** Six thrusters make it heavier than the four-thruster box; the
   budget says what the bars need to be. Ballast is as low as anything on
   the vehicle.
5. **The chassis print.** It is 300 mm across the wings. Sketchat's beds may
   be smaller; the model splits it at the box's midline with a lap joint if
   so, which is one flag in `titan.py`.
6. **Lights.** The Titan has two. None are bought; two 12 V LED cans go in
   the nose either side of the window when there is a reason to see in the
   dark.
