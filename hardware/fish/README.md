# Fish v1

A tethered swimming robot for the tank: OpenFish's tail (TU Delft, CC BY-SA
4.0, files in `../reference/openfish`) behind a head redrawn for the parts
Amazon.sa sells, with all the thinking on the surface. The DGX Spark runs the
controller; the fish carries a camera, an IMU, one motor and two steel cables.

- Build sequence, ten steps: [assembly.html](assembly.html), published at
  <https://claude.ai/code/artifact/eb47bdcd-a4e0-4a02-ae77-28644fcee136>
- What was bought, 19 September: [bom-amazon-sa.md](bom-amazon-sa.md)
- The head, as code: [params.py](params.py), [head.py](head.py); as a model you can orbit:
  <https://claude.ai/code/artifact/63102344-3233-4489-8d67-3a8907f0cede>

```bash
hardware/.venv/bin/python hardware/fish/head.py                 # STEP + STL into hardware/out/fish
RENDER_OUT=hardware/out/fish hardware/.venv/bin/python hardware/nano/render.py iso open side
```

## The head, and why it is shaped this way

OpenFish's head is two halves on a gasket, built around a Pololu 25D motor,
a 20:50 spur pair and a Huco right-angle gearbox. Reading its files changed
two things I had assumed:

- **Its head is sealed**, with the motor and electronics inside, and the
  tail cables somehow leave it. The paper does not say how.
- **Its ribs carry the cables on the horizontal midline**, in Ø1.5 holes
  21.6 mm apart, and the first rib bolts to the head with two M3 screws
  17 mm apart. Those are the numbers our head has to honour.

So ours is built so that no cable ever crosses a seal:

| Part | What it is | Seals by |
| --- | --- | --- |
| **shell** | one printed piece, nose to bulkhead, 180 mm, OpenFish's stations (61 × 75 at the widest) shortened because the motor lies along x | epoxy coat inside; window O-ring; two PG7 glands on the crown |
| **drive plate** | 8 mm plate on the shell's rear collar; motor bolted to its dry face, crank on its wet face | face O-ring 66 × 2 to the collar; 4 × 10 × 4 lip seal on the Ø4 shaft |
| **crank** | Ø30 disc on the D-shaft, one pin, three radii (6, 9, 12) | wet |
| **tail bay** | 45 mm of flooded skin behind the plate: cable guide wall, vents, the rear ring OpenFish's rib 6 bolts to | wet, nothing to seal |
| **tray** | slides in from the rear; a 5 mm grid of M2.5 holes; a cantilever carries the camera into the nose | dry |
| **bezel** | holds the 30 mm acrylic window on its O-ring | four M2 |

The **rear collar** is an external flange, 70 × 84, so the opening stays the
full inner section: the BTS7960 is 50 mm square and has to pass through it.
It reads as a gill line.

The **drive plate is a module**: plate, motor, seal, crank. It can be bolted
to a bucket lid and run under water before there is a fish, which is how the
seal gets trusted.

## The open questions, in the order they close

1. **Motor torque.** OpenFish had about 5 kg·cm at its crank through a 2.5:1
   spur pair. Our motor direct-drives at 2.2 kg·cm stall. That is why the
   crank has three radii and why step 1 of the build measures stall torque
   before anything is printed. If 6 mm of crank radius is not enough tail,
   the fallback is a 37 mm 300 rpm motor, and the plate's motor face is the
   only thing that changes.
2. **Two guesses to measure on arrival:** the motor's length (54 assumed)
   and shaft length (12 assumed); the crank needs 8 mm past the seal.
3. **The lip seal** is not ordered. 4 × 10 × 4 NBR TC from AliExpress, a
   4 × 8 × 3 as fallback; the pocket follows whichever arrives.
4. **The tail interface.** Ribs 7-9, the mould and the silicone are OpenFish's
   unchanged. Whether their rib 6 is used or the bay's rear ring replaces it
   is decided when the mould is printed and the cover's front lip is seen.
   The rib pitch in the pictures is a guess at 30 mm.
5. **Printed and porous.** PETG from Sketchat for the first fit; the shell's
   inside gets a coat of epoxy before it sees water, and the real one is MJF
   PA12 from JLC3DP, also coated.

## Mass

Printed parts in PETG: shell 160 g, plate 52, bay 61, tray 16, crank 5,
bezel 2, about 300 g. Motor 85, boards and camera about 80, window 3, seal
and screws 20. Around 490 g dry, before the tail and the trim weights.
OpenFish trims to 1,370 g; the tail and ballast make up the rest.
