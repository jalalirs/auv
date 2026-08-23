#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
source /opt/reef_ws/install/setup.bash
set -u

mkdir -p /data/logs/reef /data/runtime/reef/xpra "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"

ros2 run foxglove_bridge foxglove_bridge \
    --ros-args -p port:=8767 \
    > /data/logs/reef/foxglove.log 2>&1 &

ros2 run mola_auv_control mola_auv_joy_teleop \
    > /data/logs/reef/teleop.log 2>&1 &

exec xpra start :100 \
    --daemon=no \
    --bind-tcp=127.0.0.1:9877 \
    --html=on \
    --tcp-auth=none \
    --socket-dir=/data/runtime/reef/xpra \
    --exit-with-children=yes \
    --start-child=/usr/local/bin/start-reef \
    --notifications=no \
    --mdns=no \
    --webcam=no \
    --speaker=no \
    --microphone=no \
    --printing=no \
    --clipboard=no
