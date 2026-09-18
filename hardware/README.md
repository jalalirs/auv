# Hardware

The physical vehicles. This directory is separate from the simulator on
purpose: the simulator's session does not touch it and this one does not touch
the simulator. The two meet at one file, the vehicle's `dynamics.json`, which
this side measures and that side integrates.

## The first vehicle: nano

A Geneinno Titan at 0.55 scale, 220 × 180 × 100 mm, built the way every hobby
ROV is built: a bought acrylic tube is the dry hull and the seal, and a printed
shell around it is the shape, the structure and the thruster ducts. The shell
floods. Nothing printed holds water out.

Six micro thrusters in the Titan's layout, four vertical and two horizontal. A
battery in the tube, so it is an AUV, with a removable tether for the months
in which it cannot be trusted.

It is flown over the same ROS 2 topics the simulator's BlueROV2 publishes and
subscribes to, so a controller written against the SDK flies it unchanged.
That is the platform's claim and this is the first thing that can test it.

The design sheet, with the model you can orbit, the budget, the bill of
materials and the open items, generated from the files below:
<https://claude.ai/code/artifact/13955f93-e8ed-4b5b-ab7b-c49542d8d351>

## The model

```bash
uv venv --python 3.13 hardware/.venv
uv pip install --python hardware/.venv/bin/python build123d trimesh pillow
hardware/.venv/bin/python hardware/nano/model.py     # STEP + STL + parts.json + nano.glb into hardware/out
hardware/.venv/bin/python hardware/nano/render.py    # PNGs to look at: iso rear top open front under side
hardware/.venv/bin/python hardware/nano/budget.py    # mass against buoyancy, righting arm, thrust
hardware/.venv/bin/python hardware/nano/sheet.py     # the design sheet, out/sheet.html + nano.json
```

`nano/params.py` holds every dimension and where it came from. `nano/model.py`
is the vehicle as code: three printed parts, and the bought parts drawn for
the pictures and the clearances. `nano/bom.md` is what to buy and what it
costs. Change a number, run it, look at the picture. The STEP files in
`out/` are what gets uploaded to JLC3DP, in MJF PA12 nylon.

## Where it stands

- [x] v2, the Titan's construction read off its photograph: an orange
      capsule over the tube, a black chassis that is the capsule's lower half
      with a base plate, four arms out to vertical pods on the wings and two
      struts back to horizontal pods on the stern corners, a bezel round the
      window, two lights on the nose. Three printed parts, 495 g of nylon.
      237 × 196 × 100 mm overall.
- [x] The thruster: ApisQueen UG500, 36 mm propeller, 47 mm, 18 g, 3.9 N,
      24 USD. The pod is designed around it; the hub carries slots for any
      12–19 mm mount pattern until one is measured.
- [x] Cover to chassis: four M3 bosses on the parting line. The tube is
      held on its diameter by two ribs in each half.
- [x] Vents in the crown, a tether eye behind the centre of buoyancy, two
      ballast rails under the plate for 140 × 12 × 6 steel bars.
- [x] The budget: 1,618 g against 1,758 cm³, +136 g in fresh water, righting
      arm 8.6 mm, heave 15.7 N, surge 7.8 N. See `budget.py`.
- [x] The bill of materials, 850–1,000 USD, with the seven penetrator holes
      accounted for. See `bom.md`.
- [ ] Two guesses to measure on the day the parts arrive: `CAP_REACH`, how
      far the locking flange and cap reach past the tube, which sets where
      the window is; and `THRUSTER_MOTOR_D` with the UG500's mount pattern.
- [ ] Trim to +20 to +40 g. The bars as drawn leave +136; shorten them.
- [ ] The righting arm. 8.6 mm against the BlueROV2's 20. Move mass down:
      battery on the floor of the tube, and the ballast is already as low as
      it goes. Or accept it: a small vehicle rolls faster and rights faster.
- [ ] The inside: a sled that carries the Pi, ESCs, IMU and camera and
      slides into the tube on rails. Printed, and the next part to model.
- [ ] Electronics: bidirectional ESC firmware, PWM from the Pi, the depth
      sensor on I²C, the leak sensor, the tether as Ethernet over two pairs.
- [ ] The tank, and the overhead camera that gives ground truth.
- [ ] The vehicle's `dynamics.json` for the simulator, from measurement:
      mass on a scale, volume by displacement, drop test, thrust on a scale.
