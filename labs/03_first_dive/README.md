# Lab 03 — First Dive

## Objective

Run a sonar-equipped BlueROV2 Heavy beside a sunken ship in DAVE, entirely on
the GPU box, and inspect the live ROS graph from Foxglove on the Mac.

This is the first vertical slice of the laboratory. It proves the simulator,
vehicle dynamics, CUDA-accelerated multibeam sonar, GPU rendering, ROS/Gazebo
bridges, ArduSub, MAVROS, and local visualization before we begin writing
autonomy.

## Launch

```bash
make dive
make dive-status
make dive-topics
make view
make keyboard
```

The first launch pulls the pinned DAVE image. The GPU cannot reach Gazebo Fuel's
object storage, so `make dive` downloads three checksum-pinned models on the Mac
and transfers them to the external data directory over Tailscale. Both the image
and assets are cached for later launches. Follow startup with `make dive-logs`.

`make view` opens Foxglove Desktop when installed, otherwise the browser client.
In the browser choose **Open connection**, **Foxglove WebSocket**, and enter
`ws://localhost:18765`. Port 18765 is forwarded to the GPU bridge on remote port
8765. Then add:

- an Image panel for `/auv/overview/image` as the primary third-person view of
  the vehicle, shipwreck, seabed, and water;
- Image panels for the camera and `sonar_image` topics;
- a 3D panel for the cleaned `/auv/sonar/point_cloud` topic;
- plots for vehicle position, orientation, and IMU values;
- a Raw Messages panel for MAVROS state.

## Scene

- World: `first_dive`, adapted from DAVE's `dave_ocean_waves_sonar`
- Vehicle: `bluerov2_heavy_multibeam_sonar`
- Spawn: `(x=5, y=2, z=-14)` metres
- Target: a distorted sunken ship near `(15, 2, -16)` metres

Gazebo runs with its server-only EGL renderer. No remote desktop or X server is
required. A static overview camera inside the world renders the actual Gazebo
scene at 960 x 540 and 5 Hz, which keeps the third-person view responsive over
the Foxglove SSH tunnel without streaming a remote desktop.

## Manual driving

Run `make keyboard` in a separate Mac terminal. It opens a direct interactive
SSH session to the controller while Foxglove remains the display:

- **W/S** or **up/down arrows**: forward and reverse
- **A/D** or **left/right arrows**: yaw
- **Q/E**: strafe; **R/F**: rise and dive
- **C/X**: arm and disarm
- **H/J**: depth hold and stabilize
- **+/-**: increase or decrease the horizontal and yaw response
- **Space**: stop; **Ctrl-C**: stop, disarm, and close the controller

Hold movement keys rather than tapping them. Start with `C`, press `+` once or
twice if the default response feels slow, and keep a camera view visible.

The browser controller remains available as an alternative:

`make drive` opens DAVE's browser joystick through a second SSH tunnel at
`ws://localhost:18766`. Click **Menu** to arm and **View** to disarm. The left
stick controls forward/reverse and lateral motion; the right stick controls yaw
and vertical motion. **A** requests STABILIZE, **Y** requests ALT_HOLD, and
**B/X** increase or decrease horizontal/yaw output. Releasing a stick centers
it, and stale input is forced to neutral by the manual-control bridge.

Keep the vehicle's front camera and sonar image visible while driving. The
overview camera is fixed and the vehicle can leave its field of view.

DAVE's integrated sonar model is configured to publish all live ROS products
without its upstream per-frame CSV and timing debug output. Docker logs rotate
at 10 MiB with three files, so leaving the lab open cannot silently consume the
disk with diagnostic data.

The raw DAVE point cloud contains non-finite no-return samples and is roughly
4.9 MiB per frame. `auv_perception/sonar_point_cloud_filter` preserves the raw
topic while publishing a finite, decimated visualization cloud at 2 Hz. This
keeps the browser responsive without weakening later autonomy experiments.

## Completion check

1. The `auv-first-dive` container remains healthy and the simulation clock moves.
2. Camera, sonar image, point cloud, IMU, pose, and odometry topics publish.
3. Foxglove displays the live camera and at least one vehicle-state plot.
4. Stop the scene cleanly with `make dive-stop`.

The next lab will command the vehicle and implement depth/heading hold.
