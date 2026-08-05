# Container environment

The development image uses Ubuntu 24.04, ROS 2 Jazzy, and Gazebo Harmonic.
It includes the ROS/Gazebo bridge, Foxglove Bridge, MCAP storage, and common
colcon tooling.

The Compose service mounts the repository at `/workspace/auv`, persistent
runtime data at `/data`, uses host networking for ROS discovery, and reserves
GPU 0 by default.

Do not install project dependencies manually on the Ubuntu 20.04 GPU host.
Add them to `Dockerfile`, rebuild, and record any consequential choice under
`docs/decisions`.
