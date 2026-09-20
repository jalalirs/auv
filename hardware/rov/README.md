# Mini ROV

The first vehicle to build. A bought IP65 box is the hull, lying flat with
its clear lid up; a printed cradle holds it and carries four thrusters; the
camera looks forward through a window in the front wall; the tether comes in
through two glands in the rear wall. No battery. The DGX Spark on the
surface runs the controller over the tether, the way the platform's
controllers already run over ROS 2.

- What to buy: [bom-amazon-sa.md](bom-amazon-sa.md)
- The vehicle as code: [params.py](params.py), [rov.py](rov.py), [budget.py](budget.py)
- As a model you can orbit: <https://claude.ai/code/artifact/2d4bc2dd-2641-4756-b605-1d60cdf186a7>

```bash
hardware/.venv/bin/python hardware/rov/rov.py                    # STEP + STL into hardware/out/rov
hardware/.venv/bin/python hardware/rov/budget.py                 # mass against buoyancy
RENDER_OUT=hardware/out/rov hardware/.venv/bin/python hardware/nano/render.py iso open rear under
hardware/.venv/bin/python hardware/rov/sheet.py                  # the design sheet
```

## Why this shape

The box lies flat rather than lid-forward because a 120 × 75 face has a
third of the drag of a 200 × 120 one, and length along the direction of
travel keeps it pointing where it is pushed. The lid stays clear so the
electronics and the leak sensor can be seen without opening anything, and a
second camera can look down through it later.

Four thrusters, not six: two vertical on the sides at mid-length give heave
and roll, two horizontal at the stern give surge and yaw. That is enough to
hold depth, drive, turn and hover, and it is the same command interface the
simulator's vehicles use, a body wrench allocated to thrusters. Sideways
motion and the BlueROV2's vectored layout wait for version two.

| Part | What it is | Seals by |
| --- | --- | --- |
| **box** | LeMotech 200 × 120 × 75 ABS, clear polycarbonate lid | its own lid gasket, greased |
| **window** | 30 mm acrylic disc in the front wall, printed bezel | O-ring under the disc, silicone under the bezel |
| **glands** | two PG7 in the rear wall: Cat6 and the power pair | the glands |
| **cradle** | printed: floor frame, two cheeks, stern arms, four band saddles, ballast channels, strap slots | wet |
| **tray** | printed: a grid of M2.5 holes, feet, the camera post | dry |

## The open questions, in the order they close

1. **The duct.** The Cryfokt listing gives no duct diameter or mounting.
   The saddles are band clamps, so only the outside diameter matters; it is
   72 in the model and is measured the day the first thruster arrives. Every
   other dimension of the cradle follows from it.
2. **The box's real wall and lid thickness**, and whether its corner bosses
   are where the model puts them. Measured on arrival; the tray follows.
3. **Ballast, not foam.** The box displaces 1.8 litres and everything on it
   weighs about 1.6 kg, so the vehicle floats by 300 g before trim. Two
   steel bars under the floor bring it to a few tens of grams positive, and
   put the weight as low as it can go.
4. **The lid at depth.** IP65 is splash-rated. In a one-metre tank the lid
   sees a tenth of an atmosphere, which an IP65 gasket holds if the screws
   are even and the gasket is greased. Tested with a tissue inside for an
   hour before the first swim, and the box never goes deeper than the tank.
5. **Power on the tether.** Four thrusters at half throttle are about 10 A.
   Over 15 m of 2.5 mm² that drops about 1 V each way; the ESCs run happily
   on 10 V. Full throttle on all four at once is not a tank manoeuvre.
6. **The stern arms** hang the horizontal thrusters 40 mm behind the box.
   They are the part most likely to flex; if they do, a cross brace between
   the two saddles is one line in the model.

## Mass

Printed in PETG about 320 g; box 380; thrusters 720; electronics 170;
window, glands and screws 80; two steel bars 376. About 2.05 kg against
2.35 litres displaced: +300 g, trimmed with the bars and the wheel weights.
Righting arm 12 mm, from the bars.
