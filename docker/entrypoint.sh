#!/usr/bin/env bash
set -e

source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"

if [ -f /workspace/auv/ros2_ws/install/setup.bash ]; then
    source /workspace/auv/ros2_ws/install/setup.bash
fi

exec "$@"
