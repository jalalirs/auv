# The simulation runtime.
#
# Isaac Sim renders and integrates; OceanSim contributes the underwater sensors
# — an imaging sonar that ray-casts acoustic return, and a camera that models
# wavelength-dependent absorption and backscatter. Neither knows what a dive is.
# This image is the engine a dive is composed from, nothing more.
#
# It carries no assets. Cities and vehicles are content-addressed and arrive
# from object storage at dive time, because baking an 800 MB tank scene into
# the runtime would mean rebuilding the runtime to add a reef.

# ── OceanSim, at a pinned upstream commit, with the 6.0 port applied ─────────
#
# Cloned rather than vendored so the provenance stays honest: this is UM Field
# Robotics' work under BSD-3-Clause, and our changes are a patch that can be
# read on its own and sent upstream. The commit is pinned because "main" is not
# a version.
FROM alpine/git:2.45.2 AS oceansim

ARG OCEANSIM_REPOSITORY=https://github.com/umfieldrobotics/OceanSim.git
ARG OCEANSIM_COMMIT=2809388b5a1dba5f3ebbf7737dc1a6de90a5063a

WORKDIR /src
RUN git clone --no-checkout "${OCEANSIM_REPOSITORY}" oceansim \
    && cd oceansim \
    && git checkout --quiet "${OCEANSIM_COMMIT}"

COPY services/sim-runtime/patches/ /patches/
RUN cd oceansim \
    && git apply --verbose /patches/0001-isaac-sim-6.0.patch \
    && rm -rf .git

# ── The runtime ──────────────────────────────────────────────────────────────
FROM nvcr.io/nvidia/isaac-sim:6.0.1

# Isaac Sim ships a complete ROS 2 Jazzy Python stack — 178 packages, rclpy
# among them — but leaves it off the interpreter's path, which is why a bare
# `import rclpy` fails and why installing a distribution looks necessary when
# it is not. Naming the two directories is the whole of it.
ENV ISAACSIM_ROS_DISTRO=jazzy
ENV PYTHONPATH=/isaac-sim/exts/isaacsim.ros2.core/jazzy/rclpy
ENV LD_LIBRARY_PATH=/isaac-sim/exts/isaacsim.ros2.core/jazzy/lib
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# A dive is a simulator and an autonomy container that must find each other,
# and DDS discovery is by domain. The platform sets this per dive so that two
# dives on one host do not hear each other.
ENV ROS_DOMAIN_ID=0

# Extensions in extsUser are discovered by Kit; the directory name is the
# extension id. Owned by the image's user, because a read-only extension
# directory stops Kit writing the bytecode it expects to write.
COPY --from=oceansim --chown=1234:1234 /src/oceansim /isaac-sim/extsUser/isaacsim.oceansim

# The NVIDIA licence is accepted by whoever runs this, not by whoever builds
# it, so ACCEPT_EULA and PRIVACY_CONSENT are deliberately not set here. The
# platform sets them when it starts a dive on an operator's behalf.

# What runs a dive: it reads the brief the agent wrote, loads the place, puts
# the vehicle in it, integrates the hydrodynamics and reports what happened.
COPY --chown=1234:1234 services/sim-runtime/coral /isaac-sim/coral

# Coral City: the application somebody watches a dive in. It is not the editor,
# and it steps the same dive the headless runner steps — the schedule differs,
# the physics does not.
#
# Both go where Kit already looks: applications in apps, extensions in extsUser
# under a directory named for the extension. Owned by the image's user, because
# Kit writes bytecode into an extension directory it has loaded.
COPY --chown=1234:1234 services/sim-runtime/apps/coral_city.kit /isaac-sim/apps/coral_city.kit
COPY --chown=1234:1234 services/sim-runtime/apps/coral_city.png /isaac-sim/apps/coral_city.png
COPY --chown=1234:1234 services/sim-runtime/exts/coral.city.shell /isaac-sim/extsUser/coral.city.shell

USER 1234:1234
WORKDIR /isaac-sim

# A dive by default, because that is what this image is for. Anything else —
# a probe, the streaming application — names its own entrypoint.
ENTRYPOINT ["/isaac-sim/python.sh", "/isaac-sim/coral/dive.py"]
