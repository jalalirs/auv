# DAVE's amd64 ROS 2 image contains Jazzy, Gazebo Harmonic, ArduSub, MAVROS,
# and the DAVE workspace. Pin the digest so upstream tag changes cannot silently
# alter our lab.
FROM ioeslab/dave:ros2@sha256:f47aa89e3fb948b16dd90a47497224c0ad1e90da674ccf520d419f30004e0ed5

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG USER_UID=1000
ARG USER_GID=1000

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV GZ_VERSION=harmonic
ENV DAVE_WS=/opt/dave_ws
ENV HOME=/home/ubuntu
ENV PATH=/opt/ardusub_ws/ardupilot/Tools/autotest:/opt/ardusub_ws/ardupilot/build/sitl/bin:${PATH}
ENV GEOGRAPHICLIB_GEOID_PATH=/usr/share/GeographicLib/geoids
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ardusub_ws/ardupilot_gazebo/build
ENV GZ_SIM_RESOURCE_PATH=/opt/ardusub_ws/ardupilot_gazebo/models:/opt/ardusub_ws/ardupilot_gazebo/worlds

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        jq \
        ros-jazzy-foxglove-bridge \
        ros-jazzy-rosbag2-storage-mcap \
    && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /usr/local/bin/auv-entrypoint
RUN chmod +x /usr/local/bin/auv-entrypoint

# Ubuntu Noble's standard ubuntu user/group are UID/GID 1000. Numeric IDs keep
# bind-mounted files writable when the values are overridden for another host.
USER ${USER_UID}:${USER_GID}
WORKDIR /workspace/auv

ENTRYPOINT ["/usr/local/bin/auv-entrypoint"]
CMD ["bash"]
