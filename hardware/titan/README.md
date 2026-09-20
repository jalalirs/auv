# Mini Titan

The first vehicle to build: the Geneinno Titan's construction at 0.8 scale,
with an IP65 box as the hidden dry part, six thrusters, and the brain on the
surface. The capsule floods. The box seals.

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
| **cover** | orange, the upper half of the capsule; four vents, a tether eye; four M4 to the chassis | wet |
| **chassis** | black: the lower half of the capsule, a base plate, four arms to the wing pods, two struts to the stern pods, two cradle ribs the box sits on, ballast rails | wet |
| **box** | LeMotech 200 × 120 × 75, IP65, clear lid up, strapped to the ribs | its own gasket, greased |
| **window** | 30 mm acrylic in the box's front wall, printed bezel seen through the capsule's nose | O-ring, silicone |
| **glands** | two PG7 in the box's rear wall | the glands |
| **tray** | inside the box: a grid of M2.5 holes, feet, the camera post | dry |

Six thrusters, the Titan's layout: four vertical in the wings give heave,
roll and pitch; two horizontal at the stern give surge and yaw. That is two
more thrusters and two more ESCs than the four-thruster list, about 480 SAR,
and it is what makes it a Titan and not a box with fans.

## The open questions, in the order they close

1. **The duct.** The Cryfokt listing gives no outside diameter. Every pod is
   a band clamp sized from `DUCT_OD`, 72 in the model; measured on arrival.
2. **The box's wall, lid and corner bosses.** Measured on arrival; the tray
   and the cradle ribs follow.
3. **Trim.** Six thrusters make it heavier than the four-thruster box; the
   budget says what the bars need to be. Ballast is as low as anything on
   the vehicle.
4. **The chassis print.** It is 300 mm across the wings. Sketchat's beds may
   be smaller; the model splits it at the box's midline with a lap joint if
   so, which is one flag in `titan.py`.
5. **Lights.** The Titan has two. None are bought; two 12 V LED cans go in
   the nose either side of the window when there is a reason to see in the
   dark.
