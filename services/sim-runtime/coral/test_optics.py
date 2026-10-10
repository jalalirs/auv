"""The camera between the water and the picture."""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import optics


def test_a_flat_port_narrows_a_gopro_by_about_a_quarter_and_a_dome_does_not():
    gopro = optics.Camera()
    across_flat, _ = optics.render_tangents(gopro, 160, 90)
    dome = optics.Camera(port=optics.Port("dome"))
    across_dome, _ = optics.render_tangents(dome, 160, 90)
    # 118 degrees across in air: behind a flat port in water about 80.
    in_water = 2 * math.degrees(math.atan(across_flat / 1.01))
    assert 75 < in_water < 85
    # Behind a dome nothing bends, and a fisheye's 118 degrees cannot be
    # drawn as a pinhole at all without the edge running away: wider still.
    assert across_dome > across_flat * 2


def test_the_middle_of_the_frame_looks_straight_ahead_and_the_edge_bends():
    camera = optics.Camera()
    (mx, my), _, _ = optics.maps(camera, 161, 91)
    assert abs(mx[45, 80] - 80) < 1e-3 and abs(my[45, 80] - 45) < 1e-3
    # The frame's top row looks further out at its ends than at its middle
    # (the corners are further off the axis), so in the pinhole picture it is
    # a curve that sags in the middle: which is how a straight line in the
    # world comes out bowed in a fisheye's frame.
    top = my[5, :]
    assert top[80] > top[5] + 1 and top[80] > top[155] + 1


def test_blue_bends_more_than_red_behind_a_flat_port_so_the_corners_fringe():
    (rx, _), _, (bx, _) = optics.maps(optics.Camera(), 161, 91)
    assert abs(rx[0, 0] - bx[0, 0]) > 0.05                   # corners, where it shows
    assert abs(rx[45, 80] - bx[45, 80]) < 1e-3               # not on the axis


def test_a_red_filter_warms_the_frame_and_keeps_its_brightness():
    rng = np.random.default_rng(0)
    frame = (np.clip(np.array([0.3, 0.5, 0.55]) + rng.normal(0, 0.05, (90, 160, 3)), 0, 1) * 255).astype("uint8")
    camera = optics.Camera(filter=optics.FILTERS["red"], port=optics.Port("none"), lens=optics.Lens(model="pinhole"))
    out = optics.through(frame, camera).astype(float)
    before = frame.reshape(-1, 3).mean(0)
    after = out.reshape(-1, 3).mean(0)
    assert after[0] / after[2] > before[0] / before[2] * 1.5
    luma = np.array([0.2126, 0.7152, 0.0722])
    assert abs(luma @ after - luma @ before) < 20


def _flat(colour, wide=1280, tall=720):
    return (np.ones((tall, wide, 3)) * np.asarray(colour) * 255).astype("uint8")


def _plain(**kw):
    return optics.Camera(lens=optics.Lens(model="pinhole"), port=optics.Port("none"), **kw)


def test_noise_grows_with_iso():
    frame = _flat((0.4, 0.45, 0.5))
    low = optics.through(frame, _plain(), iso=100, seed=1).astype(float)
    high = optics.through(frame, _plain(), iso=3200, seed=1).astype(float)
    middle = (slice(340, 380), slice(600, 680))                 # away from the vignetted corners
    spread = lambda a: a[middle].reshape(-1, 3).std(0).mean()  # per channel, not across them
    assert spread(high) > 2 * spread(low)
    # And the picture stays the picture: the mean barely moves.
    assert abs(high[middle].mean() - low[middle].mean()) < 4


def test_a_red_filter_gives_a_dim_red_channel_more_signal_against_its_noise():
    # Blue water at depth: red is a sliver of what reaches the camera.
    frame = _flat((0.06, 0.45, 0.55))
    middle = (slice(340, 380), slice(600, 680))
    bare = optics.through(frame, _plain(), iso=800, seed=2).astype(float)[middle][..., 0]
    red = optics.through(frame, _plain(filter=optics.FILTERS["red"]), iso=800, seed=2).astype(float)[middle][..., 0]
    assert red.mean() / red.std() > bare.mean() / bare.std()


def test_the_corners_are_darker_than_the_middle():
    out = optics.through(_flat((0.5, 0.5, 0.5)), _plain(), iso=100, seed=3).astype(float)
    assert out[:20, :20].mean() < out[350:370, 630:650].mean() - 5


def test_no_sensor_is_the_optics_alone():
    frame = _flat((0.4, 0.45, 0.5))
    out = optics.through(frame, _plain(sensor=optics.SENSORS["none"]), iso=3200, seed=4)
    assert out.reshape(-1, 3).std(0).max() < 1.0


def test_the_dive_says_over_the_vehicle_over_the_environment_over_the_defaults():
    settings, told = optics.settings_from(vehicle={"lens": "pinhole", "lensFovDeg": 80, "port": "dome"},
                                          dive={"filter": "red", "iso": 1600},
                                          environment={"IOCEAN_PORT": "flat", "IOCEAN_SENSOR": "imx322"})
    camera = optics.camera_from(settings, told)
    assert camera.lens.model == "pinhole" and camera.lens.horizontal_fov_deg == 80
    assert camera.port.kind == "dome"                      # the vehicle over the environment
    assert camera.filter.kind == "red" and camera.iso == 1600
    assert camera.sensor.kind == "imx322"                  # nobody above the environment said
    assert told == ("environment", "vehicle", "dive")
    assert optics.camera_from(*optics.settings_from(environment={})).said()["iso"] == "auto"


def test_a_dive_reads_its_camera_from_the_vehicle_package_and_its_own_objective(tmp_path):
    import json

    (tmp_path / "dynamics.json").write_text(json.dumps({"camera": {"lens": "pinhole", "lensFovDeg": 80,
                                                                   "port": "dome", "sensor": "imx322"}}))
    plain = optics.for_dive({"objective": {"kind": "reach"}}, tmp_path)
    assert plain.port.kind == "dome" and plain.sensor.kind == "imx322"
    gopro = optics.for_dive({"objective": {"kind": "reach", "camera": {"lens": "gopro-wide", "port": "flat"}}},
                            tmp_path)
    assert gopro.lens.model == "equidistant" and gopro.port.kind == "flat" and gopro.sensor.kind == "imx322"
    # A rectilinear 80 degree lens behind a dome is drawn at exactly its own width.
    across, _ = optics.render_tangents(plain, 160, 90)
    assert abs(across / 1.01 - np.tan(np.radians(40))) < 0.01


def test_a_turn_smears_sideways_by_what_the_motion_field_says():
    du, dv = optics.motion(161, 91, 1.0, (0, 0, 0), (0, 0.6, 0), 1 / 60, 3.0)
    f = 80 / 1.0
    assert abs(abs(du[45, 80]) - f * 0.6 / 60) < 1e-3 and abs(dv[45, 80]) < 1e-6
    stripes = np.zeros((91, 161, 3), "float32")
    stripes[:, ::8] = 1.0
    out = optics.smeared(stripes, du * 8, dv * 8)                 # exaggerated, so it shows
    assert out[45].std() < stripes[45].std() * 0.8                # across: softened
    assert np.allclose(out[:, 80].std(), stripes[:, 80].std(), atol=0.05)   # down a column: as it was


def test_moving_ahead_smears_the_edges_and_leaves_the_middle():
    du, dv = optics.motion(161, 91, 1.0, (0, 0, 2.0), (0, 0, 0), 1 / 60, 3.0)
    assert abs(du[45, 80]) < 1e-6 and abs(dv[45, 80]) < 1e-6
    assert abs(du[45, 0]) > 0.5 and abs(dv[0, 80]) > 0.3


def test_no_motion_is_no_blur_and_blur_can_be_turned_off():
    frame = _flat((0.4, 0.45, 0.5), 320, 180)
    still = _plain(sensor=optics.SENSORS["none"])
    assert np.array_equal(optics.through(frame, still), optics.through(frame, still, turning=(0, 0, 0)))
    settings, told = optics.settings_from(dive={"motionBlur": False}, environment={})
    assert optics.camera_from(settings, told).motion_blur is False


def test_white_balance_is_auto_unless_a_dive_locks_it():
    assert optics.camera_from(*optics.settings_from(environment={})).white_balance == "auto"
    locked = optics.camera_from(*optics.settings_from(dive={"whiteBalance": "daylight", "filter": "red"},
                                                      environment={}))
    assert locked.white_balance == "daylight" and locked.said()["whiteBalance"] == "daylight"


def _scene(wide=640, tall=360, seed=5):
    rng = np.random.default_rng(seed)
    base = np.zeros((tall, wide, 3), "float32")
    for _ in range(60):
        x, y, r = rng.integers(0, wide), rng.integers(0, tall), rng.integers(10, 60)
        yy, xx = np.ogrid[:tall, :wide]
        base[(xx - x) ** 2 + (yy - y) ** 2 < r * r] = rng.uniform(0.1, 0.9, 3)
    base += rng.normal(0, 0.03, base.shape)
    return (np.clip(base, 0, 1) * 255).astype("uint8")


def test_sharpening_raises_the_edges_and_off_leaves_the_frame():
    import cv2

    frame = cv2.GaussianBlur(_scene(), (0, 0), 1.5)
    edges = lambda a: cv2.Laplacian(a.astype("float32").mean(2), cv2.CV_32F).std()
    assert edges(optics.sharpened(frame, 0.9)) > edges(frame) * 1.3
    assert np.array_equal(optics.sharpened(frame, 0.0), frame)


def test_fewer_bits_buy_a_lower_quality_and_more_error():
    frame = _scene()
    rich, q_rich = optics.compressed(frame, 60.0)
    poor, q_poor = optics.compressed(frame, 2.0)
    assert q_poor < q_rich
    error = lambda a: np.abs(a.astype(float) - frame.astype(float)).mean()
    assert error(poor) > error(rich) and poor.shape == frame.shape


def test_each_camera_records_at_its_own_rate_unless_told():
    assert optics.camera_from(*optics.settings_from(environment={})).video_mbps == 60.0
    own = optics.camera_from(*optics.settings_from(vehicle={"sensor": "imx322"}, environment={}))
    assert own.video_mbps == 10.0
    told = optics.camera_from(*optics.settings_from(vehicle={"sensor": "imx322"}, dive={"videoMbps": 25,
                                                                                         "sharpening": "high"},
                                                    environment={}))
    assert told.video_mbps == 25.0 and told.sharpening == 0.9
