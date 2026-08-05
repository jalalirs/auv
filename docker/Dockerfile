FROM osrf/ros:jazzy-desktop-full

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG USER_UID=1000
ARG USER_GID=1000

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV GZ_VERSION=harmonic

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        curl \
        git \
        jq \
        mesa-utils \
        python3-colcon-common-extensions \
        python3-pip \
        python3-rosdep \
        python3-vcstool \
        ros-jazzy-foxglove-bridge \
        ros-jazzy-rmw-fastrtps-cpp \
        ros-jazzy-ros-gz \
        ros-jazzy-rosbag2-storage-mcap \
        vulkan-tools \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${USER_GID}" auv \
    && useradd --create-home --uid "${USER_UID}" --gid "${USER_GID}" --shell /bin/bash auv

COPY docker/entrypoint.sh /usr/local/bin/auv-entrypoint
RUN chmod +x /usr/local/bin/auv-entrypoint

USER auv
WORKDIR /workspace/auv

ENTRYPOINT ["/usr/local/bin/auv-entrypoint"]
CMD ["bash"]
