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
```

The first launch pulls the pinned DAVE image. The GPU cannot reach Gazebo Fuel's
object storage, so `make dive` downloads three checksum-pinned models on the Mac
and transfers them to the external data directory over Tailscale. Both the image
and assets are cached for later launches. Follow startup with `make dive-logs`.

`make view` opens Foxglove Desktop when installed, otherwise the browser client.
In the browser choose **Open connection**, **Foxglove WebSocket**, and enter
`ws://localhost:18765`. Port 18765 is forwarded to the GPU bridge on remote port
8765. Then add:

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
required.

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
