"""Fly a controller live, over ROS 2.

This is the container's entry point on the platform and the way a controller
reaches a real vehicle: a node that subscribes to what the vehicle publishes,
hands the controller an observation at a steady rate, and publishes what it
answers. Its tunables are ROS parameters with ranges, so the platform's
console — or any ROS 2 tool — can list and move them without the controller
knowing that a console exists.

    python3 -m coral_city.ros my_module:MyController

Nothing here is a simulator arrangement. The topics are the vehicle's
contract, the parameters are plain rclpy, and the same process would run
beside a real vehicle's ROS 2 graph.
"""

from __future__ import annotations

import importlib
import re
import sys

import numpy as np

from .controller import Command, Controller
from .sensing import Navigator


def node_name_of(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_") or "controller"
    return cleaned if cleaned[0].isalpha() else "c_" + cleaned


def fly(controller: Controller, rate_hz: float = 20.0, args=None) -> None:
    """Run the controller until the process is told to stop."""
    import rclpy

    rclpy.init(args=args)
    node = ControllerNode(controller, rate_hz)
    try:
        rclpy.spin(node.node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


class ControllerNode:
    """The node around a controller. Built as a plain object holding an rclpy
    node rather than a subclass, so importing this module does not need ROS
    — the tank and the checks import it too."""

    def __init__(self, controller: Controller, rate_hz: float) -> None:
        from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor, SetParametersResult
        from rclpy.node import Node
        from geometry_msgs.msg import Twist, TwistWithCovarianceStamped
        from sensor_msgs.msg import FluidPressure, Imu
        from std_msgs.msg import Float64MultiArray

        self.controller = controller
        self.vehicle = controller.described
        problems = self.vehicle.check(type(controller))
        if problems:
            raise SystemExit("this controller cannot fly this vehicle: " + "; ".join(problems))

        self.node = Node(node_name_of(controller.name))
        self.navigator = Navigator()
        self.engaged = False
        self.sent = 0
        self._syncing = False

        # Tunables as ROS parameters, each with its range and its meaning, so
        # that what the controller declared is what any tool sees.
        for parameter in controller.parameters.values():
            descriptor = ParameterDescriptor(
                description=parameter.says,
                additional_constraints=parameter.unit,
                floating_point_range=[FloatingPointRange(
                    from_value=float(parameter.low), to_value=float(parameter.high), step=0.0)],
            )
            self.node.declare_parameter(parameter.name, float(parameter.value), descriptor)

        def on_set(parameters):
            if not self._syncing:
                for p in parameters:
                    if p.name in controller.parameters:
                        controller.tune(p.name, float(p.value))
            return SetParametersResult(successful=True)

        self.node.add_on_set_parameters_callback(on_set)

        # What the vehicle publishes.
        self.node.create_subscription(FluidPressure, "/depth", self._on_pressure, 10)
        self.node.create_subscription(Imu, "/imu/data", self._on_imu, 10)
        if "dvl" in self.vehicle.carries:
            self.node.create_subscription(TwistWithCovarianceStamped, "/dvl/twist", self._on_dvl, 10)

        # What it acts on.
        self._Twist, self._Floats = Twist, Float64MultiArray
        if controller.commands == "wrench":
            self.wrench_out = self.node.create_publisher(Twist, "/cmd_vel", 10)
            self.thrusters_out = None
        else:
            self.wrench_out = None
            self.thrusters_out = self.node.create_publisher(Float64MultiArray, "/thruster_cmd", 10)

        self.node.create_timer(1.0 / rate_hz, self._tick)
        self.node.get_logger().info(
            f"{controller.name} for the {self.vehicle.name}, commanding by {controller.commands}, "
            f"{len(controller.parameters)} tunable")

    # ── readings ─────────────────────────────────────────────────────────────

    def _on_pressure(self, message) -> None:
        self.navigator.pressure(message.fluid_pressure)

    def _on_imu(self, message) -> None:
        q = message.orientation
        v = message.angular_velocity
        self.navigator.imu((q.w, q.x, q.y, q.z), (v.x, v.y, v.z))

    def _on_dvl(self, message) -> None:
        v = message.twist.twist.linear
        self.navigator.dvl((v.x, v.y, v.z))

    # ── the step ─────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self.navigator.ready:
            return
        now = self.node.get_clock().now().nanoseconds / 1e9
        seen = self.navigator.observation(now)
        if not self.engaged:
            self.controller.engage(seen)
            self.engaged = True
            # A controller may settle its own targets on engagement — the
            # depth it found itself at, say. What it holds is what the
            # parameters should say, so anyone looking sees the truth.
            self.sync_parameters()
        asked = self.controller.observe(seen)
        self.publish(asked)

    def sync_parameters(self) -> None:
        from rclpy.parameter import Parameter

        self._syncing = True
        try:
            self.node.set_parameters([
                Parameter(p.name, Parameter.Type.DOUBLE, float(p.value))
                for p in self.controller.parameters.values()
            ])
        finally:
            self._syncing = False

    def publish(self, asked: Command) -> None:
        if self.wrench_out is not None:
            wrench = np.zeros(6) if asked.wrench is None else np.asarray(asked.wrench, dtype=float)
            message = self._Twist()
            message.linear.x, message.linear.y, message.linear.z = (float(v) for v in wrench[:3])
            message.angular.x, message.angular.y, message.angular.z = (float(v) for v in wrench[3:])
            self.wrench_out.publish(message)
        else:
            if asked.thrusters is None:
                return
            values = np.clip(np.asarray(asked.thrusters, dtype=float), -1.0, 1.0)
            if values.shape[0] != len(self.vehicle.thrusters):
                self.node.get_logger().error(
                    f"{values.shape[0]} thruster commands for a vehicle with {len(self.vehicle.thrusters)}")
                return
            message = self._Floats()
            message.data = [float(v) for v in values]
            self.thrusters_out.publish(message)
        self.sent += 1

    def destroy_node(self) -> None:
        self.node.destroy_node()


def load_controller(spec: str) -> Controller:
    """`module:Class`, or `module` when the module defines one controller."""
    from .loading import controller_from

    return controller_from(spec)()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python3 -m coral_city.ros module[:Class] [--rate HZ]", file=sys.stderr)
        return 2
    rate = 20.0
    if "--rate" in argv:
        at = argv.index("--rate")
        rate = float(argv[at + 1])
        argv = argv[:at] + argv[at + 2:]
    fly(load_controller(argv[0]), rate_hz=rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
