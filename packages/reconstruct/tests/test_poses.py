"""Navigation poses for a video: the frames' poses by time, COLMAP's world to
camera, and the seabed seeded under a camera."""

import sys
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from iocean_reconstruct import poses  # noqa: E402

# Looking straight down: image right is east, image down is south, the view is down.
DOWN = [0.0, 1.0, 0.0, 0.0]
K = {"model": "OPENCV", "width": 1600, "height": 900, "fx": 950.0, "fy": 955.0, "cx": 800.0, "cy": 450.0,
     "k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0}


def project(q_w2c, t, k, point):
    c = poses.rotation_of(q_w2c) @ np.asarray(point, float) + np.asarray(t)
    return k["fx"] * c[0] / c[2] + k["cx"], k["fy"] * c[1] / c[2] + k["cy"], c[2]


def test_each_frame_takes_the_nearest_pose_within_half_an_interval():
    pose_t = [0.0, 0.501, 1.002, 1.503, 3.0]
    frames = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.2]
    assert poses.nearest_in_time(frames, pose_t, 0.5) == [0, 1, 2, 3, None, None, 4]
    # The SubPipe drift: images every 0.5005 s, the video at 2 fps; frame 413 still finds its own.
    images = np.arange(414) * 0.5005
    assert poses.nearest_in_time(np.arange(414) * 0.5, images, 0.5) == list(range(414))


def test_a_camera_looking_down_sees_the_point_below_it_at_the_centre():
    centre = [12.0, -40.0, -5.0]
    q, t = poses.world_to_camera(DOWN, centre)
    u, v, depth = project(q, t, K, [12.0, -40.0, -7.5])
    assert np.allclose([u, v, depth], [800.0, 450.0, 2.5])
    # East is to the right of the image, north to the top.
    u, v, _ = project(q, t, K, [13.0, -40.0, -7.5])
    assert u > 800 and np.isclose(v, 450)
    u, v, _ = project(q, t, K, [12.0, -39.0, -7.5])
    assert v < 450 and np.isclose(u, 800)


def test_a_tilted_camera_round_trips_through_world_to_camera():
    rng = np.random.default_rng(1)
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    centre = rng.normal(size=3) * 10
    qw, t = poses.world_to_camera(q, centre)
    r = poses.rotation_of(qw)
    assert np.allclose(r, poses.rotation_of(q).T) and np.allclose(r @ centre + t, 0)


def test_the_intrinsics_are_scaled_to_the_frames():
    camera = {"model": "OPENCV", "width": 2704, "height": 1520, "fx": 1612.36, "fy": 1622.56, "cx": 1365.43,
              "cy": 741.27, "k1": -0.247, "k2": 0.0869, "p1": -0.006, "p2": 0.001}
    k = poses.intrinsics_at(camera, (1600, 900))
    assert np.isclose(k["fx"], 1612.36 * 1600 / 2704) and np.isclose(k["cy"], 741.27 * 900 / 1520)
    assert k["k1"] == -0.247 and (k["width"], k["height"]) == (1600, 900)


def test_the_seabed_is_seeded_at_the_altitude_under_the_camera():
    centre = [3.0, 4.0, -10.0]
    image = np.zeros((900, 1600, 3), np.uint8)
    image[:, :800] = [200, 100, 50]                               # the left half one colour
    xyz, rgb = poses.seabed_seeds(K, DOWN, centre, 2.0, image, grid=(32, 18))
    assert len(xyz) == 32 * 18 and np.allclose(xyz[:, 2], -12.0)
    # The footprint is the image's, at 2 m: half its width by the focal length either side.
    assert np.isclose(np.abs(xyz[:, 0] - 3.0).max(), 2.0 * (800 - 25) / 950)
    west = xyz[:, 0] < 3.0
    assert (rgb[west] == [200, 100, 50]).all() and (rgb[~west] == 0).all()
    # Every seed lands back on the pixel it came from.
    q, t = poses.world_to_camera(DOWN, centre)
    u, v, _ = project(q, t, K, xyz[0])
    assert np.allclose([u, v], [25.0, 25.0])


def test_no_bottom_lock_seeds_nothing():
    for altitude in (-1.0, 0.0, None):
        xyz, rgb = poses.seabed_seeds(K, DOWN, [0, 0, 0], altitude, None)
        assert xyz.shape == (0, 3) and rgb.shape == (0, 3)


def test_rays_over_the_horizon_or_too_far_seed_nothing():
    # Looking level, north: image down is down, so only the lower half meets the seabed.
    level = np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])
    w = np.sqrt(1 + np.trace(level)) / 2
    q = [w, (level[2, 1] - level[1, 2]) / (4 * w), (level[0, 2] - level[2, 0]) / (4 * w),
         (level[1, 0] - level[0, 1]) / (4 * w)]
    xyz, _ = poses.seabed_seeds(K, q, [0, 0, 0], 1.0, None, grid=(8, 10), reach=4.0)
    assert len(xyz) and np.allclose(xyz[:, 2], -1.0)
    assert (np.linalg.norm(xyz, axis=1) <= 4.0 + 1e-9).all() and len(xyz) < 8 * 5


def test_undistortion_inverts_the_opencv_model():
    k = dict(K, k1=-0.247, k2=0.0869, p1=-0.006, p2=0.001)
    xy = np.array([[0.3, -0.2], [-0.5, 0.25], [0.0, 0.0]])
    r2 = (xy ** 2).sum(1)
    radial = 1 + k["k1"] * r2 + k["k2"] * r2 ** 2
    x, y = xy[:, 0], xy[:, 1]
    xd = x * radial + 2 * k["p1"] * x * y + k["p2"] * (r2 + 2 * x * x)
    yd = y * radial + k["p1"] * (r2 + 2 * y * y) + 2 * k["p2"] * x * y
    uv = np.column_stack([k["fx"] * xd + k["cx"], k["fy"] * yd + k["cy"]])
    assert np.allclose(poses.undistorted(uv, k), xy, atol=1e-6)


def test_a_model_and_its_seeds_are_written_as_colmap_reads_them(tmp_path):
    q, t = poses.world_to_camera(DOWN, [0, 0, 0])
    poses.write_model(tmp_path, K, [(1, "00001.jpg", q, t), (2, "00002.jpg", q, t)])
    lines = (tmp_path / "images.txt").read_text().split("\n")
    assert lines[0].split()[-2:] == ["1", "00001.jpg"] and lines[1] == "" and lines[2].startswith("2 ")
    assert (tmp_path / "cameras.txt").read_text().startswith("1 OPENCV 1600 900 950 955 800 450")
    (tmp_path / "points3D.txt").write_text("# header\n7 0 0 0 1 2 3 0.5 1 0 2 0\n")
    assert poses.append_points(tmp_path / "points3D.txt", np.zeros((2, 3)), np.zeros((2, 3), np.uint8)) == 2
    assert [line.split()[0] for line in (tmp_path / "points3D.txt").read_text().splitlines()[1:]] == ["7", "8", "9"]


def test_the_csv_is_read_in_time_order(tmp_path):
    f = tmp_path / "poses.csv"
    f.write_text("image,t,x,y,z,qw,qx,qy,qz,altitudeM\n"
                 "b.jpg,0.5,1,2,-3,0,1,0,0,2.5\n"
                 "a.jpg,0.0,0,0,-3,0,1,0,0,\n")
    rows = poses.read_poses(f)
    assert [r["image"] for r in rows] == ["a.jpg", "b.jpg"]
    assert rows[0]["altitudeM"] is None and rows[1]["altitudeM"] == 2.5 and rows[1]["centre"] == [1.0, 2.0, -3.0]
