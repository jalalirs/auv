"""Produce a finite, lightweight sonar cloud for interactive visualization."""

from __future__ import annotations

import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
from sensor_msgs_py import point_cloud2


XYZ_FIELDS = [
    PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
    PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
    PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
]


def filter_points(
    points: np.ndarray, stride: int, max_range_m: float
) -> np.ndarray:
    """Remove invalid/out-of-range XYZ samples and decimate the survivors."""
    xyz = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    finite = xyz[np.isfinite(xyz).all(axis=1)]

    if max_range_m > 0.0 and len(finite):
        squared_range = np.einsum("ij,ij->i", finite, finite)
        finite = finite[squared_range <= max_range_m * max_range_m]

    return np.ascontiguousarray(finite[::stride], dtype="<f4")


def make_cloud(source: PointCloud2, points: np.ndarray) -> PointCloud2:
    """Pack XYZ points into a compact, standards-compliant PointCloud2."""
    cloud = PointCloud2()
    cloud.header = source.header
    cloud.height = 1
    cloud.width = len(points)
    cloud.fields = XYZ_FIELDS
    cloud.is_bigendian = False
    cloud.point_step = 12
    cloud.row_step = cloud.point_step * cloud.width
    cloud.data = points.tobytes()
    cloud.is_dense = True
    return cloud


class SonarPointCloudFilter(Node):
    """Clean and reduce DAVE's organized sonar cloud for Foxglove."""

    def __init__(self) -> None:
        super().__init__("sonar_point_cloud_filter")

        self.declare_parameter("input_topic", "/sonar/point_cloud_raw")
        self.declare_parameter("output_topic", "/auv/sonar/point_cloud")
        self.declare_parameter("stride", 8)
        self.declare_parameter("max_range_m", 10.0)
        self.declare_parameter("max_rate_hz", 2.0)

        input_topic = str(self.get_parameter("input_topic").value)
        output_topic = str(self.get_parameter("output_topic").value)
        self._stride = int(self.get_parameter("stride").value)
        self._max_range_m = float(self.get_parameter("max_range_m").value)
        max_rate_hz = float(self.get_parameter("max_rate_hz").value)

        if self._stride < 1:
            raise ValueError("stride must be at least 1")
        if max_rate_hz <= 0.0:
            raise ValueError("max_rate_hz must be positive")

        self._minimum_period_ns = int(1_000_000_000 / max_rate_hz)
        self._last_publish_ns = 0
        self._published_frames = 0

        output_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._publisher = self.create_publisher(
            PointCloud2, output_topic, output_qos
        )
        self._subscription = self.create_subscription(
            PointCloud2,
            input_topic,
            self._on_cloud,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            f"Filtering {input_topic} -> {output_topic} "
            f"(stride={self._stride}, max_rate={max_rate_hz:.1f} Hz)"
        )

    def _on_cloud(self, message: PointCloud2) -> None:
        now_ns = time.monotonic_ns()
        if now_ns - self._last_publish_ns < self._minimum_period_ns:
            return

        xyz = point_cloud2.read_points_numpy(
            message,
            field_names=["x", "y", "z"],
            skip_nans=False,
        )
        filtered = filter_points(xyz, self._stride, self._max_range_m)
        self._publisher.publish(make_cloud(message, filtered))
        self._last_publish_ns = now_ns
        self._published_frames += 1

        if self._published_frames == 1:
            self.get_logger().info(
                f"Published first visualization cloud with {len(filtered)} points"
            )


def main(args: list[str] | None = None) -> None:
    """Run the sonar point-cloud filter."""
    rclpy.init(args=args)
    node = SonarPointCloudFilter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
