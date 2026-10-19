# syntax=docker/dockerfile:1.17
#
# A controller built from its source, as the platform runs it
# (python3 -m iocean_controller_build.job '<brief>';
# services/control-plane/internal/controllerbuild).
#
# Two images from this file. `base` is what every controller's image stands
# on, the same as `iocean deploy` builds: ROS 2 Jazzy with numpy. The job
# image is that base with git, pip, the SDK, the runtime's physics (for the
# tank check) and the base itself saved as an OCI layout (base-oci/, made by
# build.sh with docker save), which the job puts the controller's layers on
# without any image builder.
#
#   bash packages/controller-build/build.sh

FROM ros:jazzy-ros-core AS base
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-numpy \
 && rm -rf /var/lib/apt/lists/*

FROM base AS job
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-pip git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY packages/sdk-python/iocean /opt/iocean/sdk/iocean
COPY services/sim-runtime/coral /opt/iocean/runtime
COPY base-oci /opt/iocean/base-oci
COPY packages/controller-build/iocean_controller_build /opt/iocean/controller-build/iocean_controller_build
RUN chmod -R a+rX /opt/iocean
ENV PYTHONPATH=/opt/iocean/controller-build \
    PYTHONUNBUFFERED=1 \
    IOCEAN_SDK=/opt/iocean/sdk \
    IOCEAN_RUNTIME=/opt/iocean/runtime \
    IOCEAN_CONTROLLER_BASE=/opt/iocean/base-oci \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    HOME=/tmp
# The sandbox runs it read-only, with no capabilities, as nobody in particular.
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT []
CMD ["python3", "-m", "iocean_controller_build.job", "--help"]
