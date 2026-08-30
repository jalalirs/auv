"""The boundary between the simulator and somebody else's autonomy.

This is the whole product, in one file. Everything else — the packages, the
governance, the hydrodynamics — exists so that a program nobody here wrote can
be handed a vehicle in some water and be unable to tell that the water is not
real.

So the rules are strict and worth stating:

  * The stack links against nothing of ours. It talks ROS 2, the same way it
    would to a vehicle, and the same binary should run on the real one.
  * The simulator publishes what the vehicle's sensors would publish and acts
    on what its thrusters would act on. Nothing else crosses.
  * Neither side waits for the other. A stack that stops commanding leaves the
    vehicle drifting, exactly as it would in the water, rather than freezing
    the simulation until it catches up.

That last one matters more than it looks. A simulator that steps only when the
controller answers is a simulator in which no controller can ever be too slow —
and being too slow is one of the main things worth finding out.
"""

from __future__ import annotations

import threading

import numpy as np


class Bridge:
    """Publishes what the vehicle senses; receives what it is told to do."""

    def __init__(self, model, allocator, domain_id: int, logger=None):
        self.model = model
        self.allocator = allocator
        self.logger = logger

        # Guarded because commands arrive on the executor's thread and are read
        # on the physics thread. A torn read of a six-element command is a
        # thruster doing something nobody asked for.
        self._lock = threading.Lock()
        self._commands = np.zeros(len(model.thrusters))
        self._commanded = False
        self._commands_seen = 0

        import rclpy
        from geometry_msgs.msg import Twist, TwistWithCovarianceStamped
        from sensor_msgs.msg import FluidPressure, Imu
        from std_msgs.msg import Float64MultiArray

        self._rclpy = rclpy
        if not rclpy.ok():
            rclpy.init(args=None, domain_id=domain_id)
        self.node = rclpy.create_node("coral_city_vehicle")

        # What the vehicle publishes. The names and types are the vehicle's
        # topic contract, which the platform checked the stack against before
        # the dive was admitted — so a stack that subscribes to something this
        # vehicle does not carry was refused rather than left waiting for a
        # message that never comes.
        self.depth = self.node.create_publisher(FluidPressure, "/depth", 10)
        self.imu = self.node.create_publisher(Imu, "/imu/data", 10)
        self.dvl = self.node.create_publisher(
            TwistWithCovarianceStamped, "/dvl/twist", 10)

        # What it acts on. Two ways of saying the same thing: per-thruster for
        # a stack that would rather allocate thrust itself, and a body wrench
        # for one that would rather not.
        self.node.create_subscription(
            Float64MultiArray, "/thruster_cmd", self._on_thrusters, 10)
        self.node.create_subscription(Twist, "/cmd_vel", self._on_wrench, 10)

        self._FluidPressure = FluidPressure
        self._Imu = Imu
        self._TwistCov = TwistWithCovarianceStamped

        self._executor = rclpy.executors.SingleThreadedExecutor()
        self._executor.add_node(self.node)
        self._spinning = threading.Thread(target=self._spin, daemon=True)
        self._stop = threading.Event()
        self._spinning.start()

    def _spin(self) -> None:
        while not self._stop.is_set():
            self._executor.spin_once(timeout_sec=0.05)

    # ── receiving ────────────────────────────────────────────────────────────

    def _on_thrusters(self, message) -> None:
        values = np.array(message.data, dtype=float)
        if values.shape[0] != len(self.model.thrusters):
            # Refused rather than padded. A stack that sends four commands to a
            # six-thruster vehicle has a bug, and quietly zeroing the other two
            # would let it fly badly instead of failing plainly.
            if self.logger:
                self.logger("command_refused",
                            why="wrong number of thrusters",
                            got=int(values.shape[0]),
                            expected=len(self.model.thrusters))
            return
        with self._lock:
            self._commands = np.clip(values, -1.0, 1.0)
            self._commanded = True
            self._commands_seen += 1

    def _on_wrench(self, message) -> None:
        """A body-frame wrench, allocated across the thrusters here.

        The allocation belongs to the vehicle rather than to whoever is flying
        it, because which thruster produces what is a property of where the
        thrusters are.
        """
        wanted = np.array([
            message.linear.x, message.linear.y, message.linear.z,
            message.angular.x, message.angular.y, message.angular.z,
        ], dtype=float)
        with self._lock:
            self._commands = self.allocator.allocate(wanted)
            self._commanded = True
            self._commands_seen += 1

    def commands(self) -> np.ndarray:
        """What the thrusters are being told to do, right now.

        Never blocks. A stack that has stopped commanding leaves the vehicle
        holding its last command and drifting, which is what would happen in
        the water; waiting for one would make a slow controller impossible to
        detect, and detecting that is half the reason to simulate at all.
        """
        with self._lock:
            return self._commands.copy()

    @property
    def commanded(self) -> bool:
        """Whether anything has ever commanded this vehicle."""
        with self._lock:
            return self._commanded

    @property
    def commands_seen(self) -> int:
        with self._lock:
            return self._commands_seen

    # ── publishing ───────────────────────────────────────────────────────────

    def publish(self, simulated_seconds: float, position: np.ndarray,
                velocity: np.ndarray, density: float) -> None:
        """What the vehicle's sensors report this step."""
        stamp = self.node.get_clock().now().to_msg()

        # A depth sensor is a pressure sensor: it reports what the water weighs
        # above it, and the vehicle works out its depth. Publishing depth
        # directly would be publishing something no real sensor produces, and a
        # stack that consumed it would not run on the vehicle.
        depth = max(float(-position[2]), 0.0)
        pressure = self._FluidPressure()
        pressure.header.stamp = stamp
        pressure.header.frame_id = "depth"
        pressure.fluid_pressure = 101325.0 + density * 9.80665 * depth
        pressure.variance = 0.0
        self.depth.publish(pressure)

        imu = self._Imu()
        imu.header.stamp = stamp
        imu.header.frame_id = "body"
        imu.angular_velocity.x = float(velocity[3])
        imu.angular_velocity.y = float(velocity[4])
        imu.angular_velocity.z = float(velocity[5])
        self.imu.publish(imu)

        twist = self._TwistCov()
        twist.header.stamp = stamp
        twist.header.frame_id = "dvl"
        twist.twist.twist.linear.x = float(velocity[0])
        twist.twist.twist.linear.y = float(velocity[1])
        twist.twist.twist.linear.z = float(velocity[2])
        self.dvl.publish(twist)

    def close(self) -> None:
        self._stop.set()
        self._spinning.join(timeout=2.0)
        try:
            self._executor.remove_node(self.node)
            self.node.destroy_node()
        except Exception:
            pass
