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
import time

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

        # What has crossed, per topic. Counted here because this is the only
        # place that knows: a count somewhere else would be a second opinion
        # about the same event, and the two would disagree the first time a
        # message was dropped.
        self._crossed: dict[str, int] = {}
        # For the rates: counts as they stood a moment ago, and when.
        self._rate_at = time.monotonic()
        self._rate_counts: dict[str, int] = {}
        self._rates: dict[str, float] = {}

        import os

        import rclpy
        from geometry_msgs.msg import Twist, TwistWithCovarianceStamped
        from sensor_msgs.msg import FluidPressure, Imu
        from std_msgs.msg import Float64MultiArray

        self._rclpy = rclpy

        # The domain comes from the environment rather than being passed here.
        #
        # Both halves of a dive are given ROS_DOMAIN_ID by the agent, and
        # passing it again as an argument is a second source of truth for the
        # same fact — one that wins over the environment, and so can put the
        # vehicle on a domain its controller is not listening to while both
        # look correctly configured. The one that the controller reads is the
        # one the vehicle should use.
        if str(domain_id) != os.environ.get("ROS_DOMAIN_ID", ""):
            os.environ["ROS_DOMAIN_ID"] = str(domain_id)
        if not rclpy.ok():
            rclpy.init(args=None)
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
        self._parameters = _StackParameters(self.node, self._lock)
        self._spinning.start()

    def _spin(self) -> None:
        turns = 0
        while not self._stop.is_set():
            self._executor.spin_once(timeout_sec=0.05)
            turns += 1
            # Every second or so, look at what the stack declares about
            # itself. Cheap when nothing has changed; the futures it raises
            # are completed by the very spin this loop is doing.
            if turns % 20 == 0:
                self._parameters.poll()

    # ── the stack's own parameters ───────────────────────────────────────────

    def parameters(self) -> list[dict]:
        """What the stack lets a hand move, as it declared it over ROS 2."""
        return self._parameters.declared()

    def set_parameter(self, name: str, value: float) -> bool:
        return self._parameters.set(name, value)

    @property
    def stack_node(self) -> str | None:
        return self._parameters.remote

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
            self._crossed["/thruster_cmd"] = self._crossed.get("/thruster_cmd", 0) + 1

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
            self._crossed["/cmd_vel"] = self._crossed.get("/cmd_vel", 0) + 1

    def topics(self) -> list[dict]:
        """What this vehicle carries, and how much has crossed each.

        The contract, as it actually stands rather than as it was declared —
        which is the useful version when something is not arriving and the
        question is whether it was ever published.
        """
        with self._lock:
            crossed = dict(self._crossed)
        now = time.monotonic()
        if now - self._rate_at >= 1.0:
            for name, count in crossed.items():
                self._rates[name] = (count - self._rate_counts.get(name, 0)) / (now - self._rate_at)
            self._rate_counts = crossed
            self._rate_at = now
        return [
            {"name": name, "type": kind, "way": way,
             "messages": crossed.get(name, 0),
             "rateHz": round(self._rates.get(name, 0.0), 1)}
            for name, kind, way in (
                ("/depth", "sensor_msgs/msg/FluidPressure", "from"),
                ("/imu/data", "sensor_msgs/msg/Imu", "from"),
                ("/dvl/twist", "geometry_msgs/msg/TwistWithCovarianceStamped", "from"),
                ("/thruster_cmd", "std_msgs/msg/Float64MultiArray", "to"),
                ("/cmd_vel", "geometry_msgs/msg/Twist", "to"),
            )
        ]

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
                velocity: np.ndarray, density: float,
                rotation: np.ndarray | None = None) -> None:
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
        if rotation is not None:
            # An IMU on a vehicle carries an attitude solution as well as
            # rates, and a controller that has to hold a heading needs one.
            # Body-to-world, as the message defines it.
            w, x, y, z = _quaternion(rotation)
            imu.orientation.w, imu.orientation.x = w, x
            imu.orientation.y, imu.orientation.z = y, z
        self.imu.publish(imu)

        twist = self._TwistCov()
        twist.header.stamp = stamp
        twist.header.frame_id = "dvl"
        twist.twist.twist.linear.x = float(velocity[0])
        twist.twist.twist.linear.y = float(velocity[1])
        twist.twist.twist.linear.z = float(velocity[2])
        self.dvl.publish(twist)

        with self._lock:
            for name in ("/depth", "/imu/data", "/dvl/twist"):
                self._crossed[name] = self._crossed.get(name, 0) + 1

    def close(self) -> None:
        self._stop.set()
        self._spinning.join(timeout=2.0)
        try:
            self._executor.remove_node(self.node)
            self.node.destroy_node()
        except Exception:
            pass


def _quaternion(rotation: np.ndarray) -> tuple[float, float, float, float]:
    """A rotation matrix as w, x, y, z. Shepperd's method, which stays
    well-conditioned whichever component is largest."""
    m = rotation
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = (trace + 1.0) ** 0.5 * 2.0
        return (0.25 * s, float(m[2, 1] - m[1, 2]) / s,
                float(m[0, 2] - m[2, 0]) / s, float(m[1, 0] - m[0, 1]) / s)
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = (1.0 + m[0, 0] - m[1, 1] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[2, 1] - m[1, 2]) / s, 0.25 * s,
                float(m[0, 1] + m[1, 0]) / s, float(m[0, 2] + m[2, 0]) / s)
    if m[1, 1] > m[2, 2]:
        s = (1.0 + m[1, 1] - m[0, 0] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[0, 2] - m[2, 0]) / s, float(m[0, 1] + m[1, 0]) / s,
                0.25 * s, float(m[1, 2] + m[2, 1]) / s)
    s = (1.0 + m[2, 2] - m[0, 0] - m[1, 1]) ** 0.5 * 2.0
    return (float(m[1, 0] - m[0, 1]) / s, float(m[0, 2] + m[2, 0]) / s,
            float(m[1, 2] + m[2, 1]) / s, 0.25 * s)


class _StackParameters:
    """What the stack on the other side declares a hand may move.

    Found the way any ROS 2 tool would find it: the stack's node declares
    parameters with ranges and descriptions, and this asks that node for
    them through its parameter services. Nothing of ours is needed on the
    stack's side — a node written with plain rclpy that declares a float
    parameter with a floating_point_range shows up here with a slider.

    Driven from the executor's own thread in small steps, because the futures
    the parameter client returns are completed by that executor spinning,
    and waiting on one from inside it would wait forever.
    """

    def __init__(self, node, lock) -> None:
        self.node = node
        self.lock = lock
        self.remote: str | None = None
        self.client = None
        self._names: list[str] = []
        self._pending = None          # (what, future)
        self._described: dict[str, dict] = {}
        self._values: dict[str, float] = {}
        self._declared: list[dict] = []

    def declared(self) -> list[dict]:
        with self.lock:
            return list(self._declared)

    def set(self, name: str, value: float) -> bool:
        if self.client is None:
            return False
        with self.lock:
            if name not in self._values:
                return False
        try:
            from rclpy.parameter import Parameter
            self.client.set_parameters([Parameter(name, Parameter.Type.DOUBLE, float(value))])
            with self.lock:
                self._values[name] = float(value)
                self._compose()
            return True
        except Exception:
            return False

    def poll(self) -> None:
        try:
            self._poll()
        except Exception:
            # A stack that vanished mid-question is a stack that vanished;
            # the next poll starts again from discovery.
            self._pending = None
            self.client = None
            self.remote = None

    def _poll(self) -> None:
        if self.client is None:
            mine = self.node.get_name()
            others = [name for name, namespace in self.node.get_node_names_and_namespaces()
                      if name != mine and not name.startswith("_")]
            if not others:
                return
            from rclpy.parameter_client import AsyncParameterClient
            self.remote = others[0]
            self.client = AsyncParameterClient(self.node, self.remote)
            self._pending = ("list", self.client.list_parameters())
            return
        if self._pending is None:
            self._pending = ("list", self.client.list_parameters())
            return
        what, future = self._pending
        if not future.done():
            return
        result = future.result()
        if what == "list":
            names = [n for n in result.result.names if not n.startswith("use_sim_time")] if result else []
            self._names = names
            self._pending = ("describe", self.client.describe_parameters(names)) if names else None
        elif what == "describe":
            self._described = {}
            for name, descriptor in zip(self._names, result.descriptors):
                # Only what a hand can move: floating point with a range.
                if descriptor.type != 3 or not descriptor.floating_point_range:
                    continue
                span = descriptor.floating_point_range[0]
                self._described[name] = {
                    "name": name, "low": float(span.from_value), "high": float(span.to_value),
                    "unit": descriptor.additional_constraints, "says": descriptor.description,
                }
            names = list(self._described)
            self._pending = ("get", self.client.get_parameters(names)) if names else None
            if not names:
                with self.lock:
                    self._declared = []
        elif what == "get":
            with self.lock:
                self._values = {}
                for name, value in zip(list(self._described), result.values):
                    self._values[name] = float(value.double_value)
                self._compose()
            self._pending = None

    def _compose(self) -> None:
        self._declared = [
            {**described, "value": round(self._values.get(name, 0.0), 4)}
            for name, described in self._described.items()
        ]
