# Mini Titan

The first vehicle to build: the Geneinno Titan's construction at 0.8 scale.
A domed orange capsule 100 mm wide and 85 tall on a black chassis, its tail
reaching back over the stern; six thrusters in pods on long arms; one tether
into a connector dome on the crown and nothing else on the skin. The dry part
is the small IP65 box, 158 × 89 × 58, lying inside the capsule with foam
above, below, ahead and behind it. The capsule floods. The box seals.

- What to buy: [bom-amazon-sa.md](bom-amazon-sa.md)
- The vehicle as code: [params.py](params.py), [titan.py](titan.py), [budget.py](budget.py)
- As a model you can orbit: <https://claude.ai/code/artifact/23a7dfa7-e69e-4d9a-b4c5-d4e82dce79e7>

```bash
hardware/.venv/bin/python hardware/titan/titan.py                 # STEP + STL into hardware/out/titan
hardware/.venv/bin/python hardware/titan/budget.py
RENDER_OUT=hardware/out/titan hardware/.venv/bin/python hardware/nano/render.py iso open rear under
hardware/.venv/bin/python hardware/titan/sheet.py
```

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
| **box** | LeMotech 158 × 89 × 58 (the 6.2 × 3.5 × 2.3 in size), IP65, lying flat, lid up, held by two ribs in the chassis | its own gasket, greased |
| **window** | 30 mm acrylic in the box's front wall, printed bezel seen through the capsule's nose | O-ring, silicone |
| **the one tether** | round Cat6, Ethernet on two pairs and 48 V on the other two, into one PG9 through the box's lid under the cover's dome | the gland |
| **foam** | closed-cell, cut from a pool noodle: a sheet above the lid, a sheet under the floor, blocks in the nose and the tail | wet; it is what floats the six thrusters |
| **tray** | inside the box: two decks on standoffs, ESCs and the converter below, the small boards above | dry |

Six thrusters, the Titan's layout: four vertical in the wings give heave,
roll and pitch; two horizontal at the stern give surge and yaw. That is two
more thrusters and two more ESCs than the four-thruster list, about 480 SAR,
and it is what makes it a Titan and not a box with fans.

## The open questions, in the order they close

1. **48 V on Cat6.** Passive PoE at 48 V and 3 A is common practice and
   inside the cable's rating, but the RJ45 plugs get warm at 3 A; the
   connection at the box is soldered, not a plug. The step-down converter
   is the one part in the box that gets hot; it sits against the floor wall.
2. **The duct.** The Cryfokt listing gives no outside diameter. Every pod is
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
