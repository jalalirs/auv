"""Hold a depth.

Written as it would be for the vehicle rather than for a simulator. It links
against nothing of Coral City's, imports nothing from it, and would not behave
differently if the water were real — which is the point of the whole platform:
the same binary should run in a tank and in the sea.

What it knows about the vehicle is what the vehicle's topic contract says: it
reads pressure and works out depth, and it writes six thruster commands. It has
never heard of a simulator.
"""

import os
import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import FluidPressure
from std_msgs.msg import Float64MultiArray

SURFACE_PRESSURE = 101325.0
DENSITY = 1025.0
GRAVITY = 9.80665

# The two vertical thrusters, in the order the vehicle lists them.
VERTICAL = (4, 5)


class DepthHold(Node):
    """A depth controller, and nothing else.

    Proportional-derivative on depth error. Deliberately simple: what is being
    demonstrated is that somebody else's program can fly this vehicle, not that
    this is a good controller. A good one would model the thruster deadband and
    the vehicle's own buoyancy, and would be a worse example for being longer.
    """

    def __init__(self, wanted_depth: float) -> None:
        super().__init__("depth_hold")
        self.wanted = wanted_depth
        self.previous_error = None
        self.commands = 0

        self.thrusters = self.create_publisher(
            Float64MultiArray, "/thruster_cmd", 10)
        self.create_subscription(FluidPressure, "/depth", self.on_pressure, 10)

        self.get_logger().info(f"holding {wanted_depth:.2f} m")

    def on_pressure(self, message: FluidPressure) -> None:
        # A depth sensor is a pressure sensor. Working the depth out here rather
        # than being handed it is what makes this the same program that would
        # run on the vehicle.
        depth = (message.fluid_pressure - SURFACE_PRESSURE) / (DENSITY * GRAVITY)

        error = self.wanted - depth
        derivative = 0.0 if self.previous_error is None else error - self.previous_error
        self.previous_error = error

        # Positive lifts. Error is positive when the vehicle is too shallow, so
        # it must descend, so the command is negative.
        effort = -(2.5 * error + 12.0 * derivative)
        effort = max(-1.0, min(1.0, effort))

        command = Float64MultiArray()
        command.data = [0.0] * 6
        for index in VERTICAL:
            command.data[index] = effort
        self.thrusters.publish(command)

        self.commands += 1
        if self.commands % 40 == 0:
            self.get_logger().info(
                f"depth {depth:.3f} m  error {error:+.3f}  effort {effort:+.3f}")


def main() -> int:
    wanted = float(os.environ.get("HOLD_DEPTH_M", "2.0"))
    rclpy.init(args=None)
    node = DepthHold(wanted)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
