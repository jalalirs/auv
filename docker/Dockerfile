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
ENV CUDA_HOME=/usr/local/cuda-12.6
ENV PATH=/usr/local/cuda-12.6/bin:/opt/ardusub_ws/ardupilot/Tools/autotest:/opt/ardusub_ws/ardupilot/build/sitl/bin:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/cuda-12.6/lib64
ENV GEOGRAPHICLIB_GEOID_PATH=/usr/share/GeographicLib/geoids
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ardusub_ws/ardupilot_gazebo/build
ENV GZ_SIM_RESOURCE_PATH=/opt/ardusub_ws/ardupilot_gazebo/models:/opt/ardusub_ws/ardupilot_gazebo/worlds

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        jq \
        ros-jazzy-foxglove-bridge \
        ros-jazzy-rosbag2-storage-mcap \
    && rm -rf /var/lib/apt/lists/*

# The upstream DAVE image contains the multibeam source, but its build skipped
# the plugin because CUDA was absent. Install only the compiler and libraries
# required by that plugin, then rebuild the two sonar packages for GPU 0's Ada
# architecture (SM 8.9).
RUN curl --fail --location --retry 8 --retry-all-errors \
        --output /tmp/cuda-keyring.deb \
        https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i /tmp/cuda-keyring.deb \
    && rm -f /tmp/cuda-keyring.deb \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        cuda-compiler-12-6 \
        libcublas-dev-12-6 \
        libcufft-dev-12-6 \
    && rm -rf /var/lib/apt/lists/*

# DAVE includes cuRAND's device headers directly. Keep this in a separate
# layer so adding the missed header package does not invalidate the cached
# compiler, cuBLAS, and cuFFT download above.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libcurand-dev-12-6 \
    && rm -rf /var/lib/apt/lists/*

RUN source /opt/ros/jazzy/setup.bash \
    && source /opt/dave_ws/install/setup.bash \
    && cd /opt/dave_ws \
    && colcon build \
        --symlink-install \
        --executor sequential \
        --packages-select multibeam_sonar multibeam_sonar_system \
        --cmake-clean-cache \
        --cmake-args \
            -DCMAKE_CUDA_ARCHITECTURES=89 \
            -DCUDA_ARCHITECTURE=89 \
            -DCUDAToolkit_ROOT=/usr/local/cuda-12.6

# The upstream integrated BlueROV2 model enables per-frame CSV dumps and CUDA
# timing prints. At simulation rate those diagnostic defaults generate hundreds
# of megabytes per minute. The ROS sonar image and point-cloud streams remain on.
RUN sed -i \
        -e 's#<writeLog>true</writeLog>#<writeLog>false</writeLog>#' \
        -e 's#<debugFlag>true</debugFlag>#<debugFlag>false</debugFlag>#' \
        /opt/dave_ws/src/dave/models/dave_robot_models/description/bluerov2_heavy_multibeam_sonar/model.sdf \
    && grep -q '<writeLog>false</writeLog>' \
        /opt/dave_ws/src/dave/models/dave_robot_models/description/bluerov2_heavy_multibeam_sonar/model.sdf \
    && grep -q '<debugFlag>false</debugFlag>' \
        /opt/dave_ws/src/dave/models/dave_robot_models/description/bluerov2_heavy_multibeam_sonar/model.sdf

COPY docker/entrypoint.sh /usr/local/bin/auv-entrypoint
RUN chmod +x /usr/local/bin/auv-entrypoint

# Ubuntu Noble's standard ubuntu user/group are UID/GID 1000. Numeric IDs keep
# bind-mounted files writable when the values are overridden for another host.
USER ${USER_UID}:${USER_GID}
WORKDIR /workspace/auv

ENTRYPOINT ["/usr/local/bin/auv-entrypoint"]
CMD ["bash"]
