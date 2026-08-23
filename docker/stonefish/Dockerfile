FROM ros:jazzy-ros-base-noble

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG USER_UID=1000
ARG USER_GID=1000
ARG BUILD_JOBS=8
ARG STONEFISH_COMMIT=b21eb8e194c570ff2f61e91aeffb38d73dc25f42
ARG MBARI_COMMIT=e2051805dccba6631986c6703a8245d2e6c285eb
ARG VIRTUALGL_VERSION=3.1.5

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV HOME=/home/ubuntu
ENV REEF_WS=/opt/reef_ws
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display,video

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        dbus-x11 \
        ffmpeg \
        libfreetype6-dev \
        libgl1-mesa-dri \
        libglm-dev \
        libsdl2-dev \
        mesa-utils \
        python3-numpy \
        python3-opencv \
        python3-pip \
        ros-jazzy-cv-bridge \
        ros-jazzy-foxglove-bridge \
        ros-jazzy-image-transport \
        ros-jazzy-joy \
        ros-jazzy-pcl-conversions \
        ros-jazzy-robot-state-publisher \
        ros-jazzy-rosidl-default-generators \
        ros-jazzy-tf2-ros \
        ros-jazzy-xacro \
        unzip \
        xpra \
        xserver-xorg-video-dummy \
    && rm -rf /var/lib/apt/lists/*

# VirtualGL's EGL backend lets the OpenGL application render on the NVIDIA GPU
# while Xpra owns only the lightweight 2D display and video transport.
RUN curl --fail --location --retry 8 --retry-all-errors \
        --output /tmp/virtualgl.deb \
        "https://github.com/VirtualGL/virtualgl/releases/download/${VIRTUALGL_VERSION}/virtualgl_${VIRTUALGL_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install --yes --no-install-recommends /tmp/virtualgl.deb \
    && rm -f /tmp/virtualgl.deb \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/stonefish-src \
    && curl --fail --location --retry 8 --retry-all-errors \
        "https://github.com/patrykcieslak/stonefish/archive/${STONEFISH_COMMIT}.tar.gz" \
        | tar --extract --gzip --strip-components=1 --directory=/tmp/stonefish-src \
    && cmake \
        -S /tmp/stonefish-src \
        -B /tmp/stonefish-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DEMBED_RESOURCES=ON \
    && cmake --build /tmp/stonefish-build --parallel "${BUILD_JOBS}" \
    && cmake --install /tmp/stonefish-build \
    && mkdir -p /usr/share/doc/stonefish \
    && cp /tmp/stonefish-src/COPYING.txt /usr/share/doc/stonefish/ \
    && rm -rf /tmp/stonefish-src /tmp/stonefish-build

# The basic branch contains the MOLA vehicle, coral assets, and Stonefish ROS 2
# wrapper without the experimental SLAM workspace from upstream main. Repair
# its malformed reef settings and propeller OBJs that reference absent MTLs.
RUN mkdir -p /tmp/mbari-src "${REEF_WS}/src" \
    && curl --fail --location --retry 8 --retry-all-errors \
        "https://github.com/AlePuglisi/MBARI-vehicles-sim-ros2/archive/${MBARI_COMMIT}.tar.gz" \
        | tar --extract --gzip --strip-components=1 --directory=/tmp/mbari-src \
    && cp -a /tmp/mbari-src/stonefish_ws/src/MOLA_AUV "${REEF_WS}/src/" \
    && cp -a /tmp/mbari-src/stonefish_ws/src/thirdparty/stonefish_ros2 "${REEF_WS}/src/" \
    && mkdir -p /usr/share/doc/mbari-vehicles-sim \
    && cp /tmp/mbari-src/LICENSE /usr/share/doc/mbari-vehicles-sim/ \
    && sed -i \
        -e 's#normal_map="sand_floor/texture/normal4k.png"#normal_map="sand_floor/texture/normal4k_compressed.png"#' \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/scenarios/materials_looks.scn" \
    && sed -i 's/scale="2\.5\.0"/scale="2.5"/' \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/scenarios/corals.scn" \
    && sed -i -e '/^mtllib /d' -e '/^usemtl /d' -e '/^l /d' \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/mola_auv/mesh/ccw.obj" \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/mola_auv/mesh/cw.obj" \
    && rm -rf /tmp/mbari-src

# Add a small public-domain fish pack as visual, deterministic moving actors.
# Scenario looks replace the source MTL files, which are not copied.
RUN mkdir -p "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/fish/mesh" \
    && curl --fail --location --retry 8 --retry-all-errors \
        --output /tmp/fish.zip \
        'https://opengameart.org/sites/default/files/Animated%20Fish%20Pack%20by%20%40Quaternius.zip' \
    && echo 'c56a4bf3468e900ed9d881037334152dc203f93b656373347c8a7fc3dedb1855  /tmp/fish.zip' \
        | sha256sum --check --strict \
    && unzip -j /tmp/fish.zip \
        'Animated Fish Pack by @Quaternius/OBJ/Fish1.obj' \
        'Animated Fish Pack by @Quaternius/OBJ/Fish2.obj' \
        'Animated Fish Pack by @Quaternius/OBJ/Fish3.obj' \
        'Animated Fish Pack by @Quaternius/OBJ/Manta ray.obj' \
        'Animated Fish Pack by @Quaternius/OBJ/Shark.obj' \
        -d "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/fish/mesh" \
    && mkdir -p /usr/share/doc/quaternius-fish \
    && unzip -p /tmp/fish.zip 'Animated Fish Pack by @Quaternius/License.txt' \
        > /usr/share/doc/quaternius-fish/LICENSE \
    && mv "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/fish/mesh/Manta ray.obj" \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/fish/mesh/MantaRay.obj" \
    && sed -i -e '/^mtllib /d' -e '/^usemtl /d' -e '/^l /d' \
        "${REEF_WS}/src/MOLA_AUV/mola_auv_sim/data/fish/mesh/"*.obj \
    && rm -f /tmp/fish.zip

COPY docker/stonefish/scenarios/living_reef.scn \
    ${REEF_WS}/src/MOLA_AUV/mola_auv_sim/scenarios/living_reef.scn
COPY docker/stonefish/scenarios/fish_school.scn \
    ${REEF_WS}/src/MOLA_AUV/mola_auv_sim/scenarios/fish_school.scn

RUN source /opt/ros/jazzy/setup.bash \
    && cd "${REEF_WS}" \
    && colcon build \
        --merge-install \
        --executor sequential \
        --packages-up-to mola_auv_sim mola_auv_control \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && rm -rf "${REEF_WS}/build" "${REEF_WS}/log"

COPY docker/stonefish/start-reef /usr/local/bin/start-reef
COPY docker/stonefish/entrypoint.sh /usr/local/bin/reef-entrypoint
RUN chmod +x /usr/local/bin/start-reef /usr/local/bin/reef-entrypoint \
    && mkdir -p /data /home/ubuntu \
    && chown "${USER_UID}:${USER_GID}" /data /home/ubuntu

USER ${USER_UID}:${USER_GID}
WORKDIR /workspace/auv

ENTRYPOINT ["/usr/local/bin/reef-entrypoint"]
