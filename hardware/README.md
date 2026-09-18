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

## The model

```bash
uv venv --python 3.13 hardware/.venv
uv pip install --python hardware/.venv/bin/python build123d trimesh matplotlib
hardware/.venv/bin/python hardware/nano/model.py     # STEP + STL into hardware/out
hardware/.venv/bin/python hardware/nano/render.py    # PNGs to look at
```

`nano/params.py` holds every dimension and where it came from. `nano/model.py`
is the shell as code. Change a number, run it, look at the picture. The STEP
files in `out/` are what gets uploaded to JLC3DP, in MJF PA12 nylon.

## Where it stands

- [x] Shell v1: the Titan's form as a loft of rounded sections, full width
      over the wings and tapering to the nose; the tube bore; two bulkheads;
      four vertical ducts in the wings and two horizontal pods overhanging
      the stern corners; split top and bottom on the tube axis. 251 g of
      nylon per half, which floods and so is nearly neutral in water (PA12 is
      1.01 g/cm³). 240 mm overall with the pods, 190 wide, 100 tall.
- [ ] The thruster. The duct diameter is a placeholder until one unit is
      chosen and measured.
- [ ] The cap reach. `CAP_REACH` is a guess at how far the locking flange
      and cap extend past the tube; check it against Blue Robotics' CAD.
- [ ] The rest of the Titan's look: a raised spine on the top, the window
      bezel, the light housings. Styling, and it waits for the parts that
      set dimensions.
- [ ] How the halves fasten, and how the tube is clamped in the bulkheads.
- [ ] Flooding vents, so the shell fills and empties without trapping air.
- [ ] Electronics layout inside the tube: Pi, battery, ESCs, IMU, depth,
      camera. Six penetrators need the 7-hole aluminium rear cap.
- [ ] The tank, and the overhead camera that gives ground truth.
