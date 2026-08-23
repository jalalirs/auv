# Lab 04 — Living Reef

## Objective

Drive a MOLA AUV through a populated coral reef in Stonefish while observing
the simulator's real graphical window, camera, sonar, vehicle state, and water
dynamics from the Mac.

This is a separate simulator track from Project 001. Starting it stops the DAVE
container so its CPU-heavy multibeam model cannot starve the reef simulation.

## Launch

The first build downloads and compiles pinned Stonefish and ROS 2 sources. It
is intentionally a larger one-time build.

```bash
make reef
make reef-status
make reef-logs       # use this if the first startup is still progressing
make reef-view       # opens the actual simulator window in the browser
make reef-keyboard   # run in another Mac terminal
```

`make reef-view` creates SSH tunnels for two separate products:

- `http://localhost:19877/` is the interactive Stonefish GUI streamed by Xpra;
- `ws://localhost:18767` is its Foxglove WebSocket for ROS-native panels.

The GUI is rendered on GPU 0 through VirtualGL's EGL backend. Xpra transports
the finished window, so the Mac does not need Linux OpenGL or a remote desktop.

## Keyboard

- **W/S** or **up/down arrows**: forward and reverse
- **A/D** or **left/right arrows**: yaw
- **Q/E**: strafe; **R/F**: rise and dive
- **+/-**: command scale from 20% to 100%
- **L**: toggle vehicle lights
- **Space**: stop; **Ctrl-C**: stop and close the controller

Stonefish does not emulate an ArduSub flight controller in this lab, so the
thrusters do not require arming. The keyboard commands MOLA's eight-thruster
allocator directly and publishes neutral output after stale input.

## What is physically simulated

- six-degree-of-freedom rigid-body motion and collision;
- geometry-derived buoyancy, added mass, drag, and hydrodynamic forces;
- individual thruster rotor and thrust dynamics;
- 1027 kg/m³ seawater, a 0.2 m/s background current, a localized 0.4 m/s jet,
  surface waves, and suspended particles;
- wavelength-dependent underwater absorption and scattering;
- camera, forward-looking sonar, DVL, IMU, pressure, and odometry.

The MOLA geometry and mass distribution are realistic research approximations,
not a validated digital twin. The fish are deterministic animated bodies on
smooth trajectories. They appear in camera/sonar data and can become tracking
targets, but their swimming is not a biological fluid-dynamics simulation.

## World contents

- textured sand terrain and multiple coral species;
- a calibration marker for visual localization experiments;
- three small schooling-fish types, a manta ray, and a reef shark;
- a neutrally buoyant eight-thruster MOLA AUV with lights and sensors.

The fish meshes come from Quaternius's CC0 Animated Fish Pack. The vehicle and
reef assets come from the MIT-licensed unofficial MBARI vehicle simulation.
Stonefish itself is GPL-3.0.

## Completion check

1. The Xpra page shows Stonefish's rendered reef rather than a reconstructed
   ROS point cloud.
2. Holding **W** changes MOLA odometry and visibly moves the AUV.
3. Corals and at least one moving animal appear in the GUI or vehicle camera.
4. Camera, FLS sonar, DVL, IMU, pressure, and odometry topics publish.
5. `make reef-stop` stops the simulator and `make reef-view-stop` closes both
   tunnels.
