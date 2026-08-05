# auv_simulation

Owns simulation-specific behavior:

- Gazebo worlds and model spawning;
- buoyancy, drag, currents, and thruster plugins;
- simulated cameras, IMU, depth, DVL, and sonar;
- Gazebo-to-ROS topic bridges; and
- ground-truth topics used only for evaluation.

Simulation truth must remain separate from observations available to the
autonomy stack.
