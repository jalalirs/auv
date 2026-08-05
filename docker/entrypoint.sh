#!/usr/bin/env bash
set -e

source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"

if [ -f /opt/dave_ws/install/setup.bash ]; then
    source /opt/dave_ws/install/setup.bash
fi

# Gazebo Fuel's object store is not reachable from the GPU network. Project
# assets are checksum-verified on the Mac and stored under the mounted data dir.
export GZ_SIM_RESOURCE_PATH="/data/gazebo/first_dive/models:${GZ_SIM_RESOURCE_PATH:-}"

if [ -f /workspace/auv/ros2_ws/install/setup.bash ]; then
    source /workspace/auv/ros2_ws/install/setup.bash
fi

exec "$@"
