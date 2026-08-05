# Container environment

The development image uses a digest-pinned DAVE ROS 2 base with Ubuntu 24.04,
ROS 2 Jazzy, Gazebo Harmonic, ArduSub, and MAVROS. Our thin layer adds Foxglove
Bridge and MCAP storage. The immutable base digest is recorded in
`docker/versions.env`.

The Compose service mounts the repository at `/workspace/auv`, persistent
runtime data at `/data`, uses host networking for ROS discovery, and reserves
GPU 0 by default.

Do not install project dependencies manually on the Ubuntu 20.04 GPU host.
Add them to `Dockerfile`, rebuild, and record any consequential choice under
`docs/decisions`.
