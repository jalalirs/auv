# ROS 2 workspace

This is the repository's only colcon workspace. Source packages live under
`src`; generated `build`, `install`, and `log` directories are ignored.

Build inside the development container:

```bash
cd /workspace/auv/ros2_ws
rosdep install --from-paths src --ignore-src --rosdistro jazzy -y
colcon build --symlink-install
source install/setup.bash
```

Package boundaries should follow ownership of runtime behavior. Do not create a
new package merely to hold a few related files.
