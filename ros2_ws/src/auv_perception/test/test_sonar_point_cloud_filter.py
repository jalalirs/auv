import numpy as np

from auv_perception.sonar_point_cloud_filter import filter_points


def test_filter_points_removes_nonfinite_range_and_applies_stride():
    points = np.array(
        [
            [1.0, 0.0, 0.0],
            [np.inf, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [np.nan, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )

    filtered = filter_points(points, stride=2, max_range_m=10.0)

    np.testing.assert_array_equal(
        filtered,
        np.array([[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]], dtype=np.float32),
    )
    assert filtered.flags.c_contiguous
