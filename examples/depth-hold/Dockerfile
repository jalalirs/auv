# A depth-holding controller, as somebody bringing their own autonomy would
# build it.
#
# Built on the ROS 2 distribution rather than on anything of ours: it has no
# dependency on Coral City, cannot import from it, and the platform runs it as
# untrusted code — no docker socket, no host network, egress denied.
FROM ros:jazzy-ros-core

COPY hold.py /opt/hold.py

# The vehicle publishes pressure and acts on thruster commands. Nothing else
# passes between them.
ENV HOLD_DEPTH_M=2.0

ENTRYPOINT ["/bin/bash", "-lc", "source /opt/ros/jazzy/setup.bash && exec python3 /opt/hold.py"]
