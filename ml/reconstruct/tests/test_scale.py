"""The reconstruction's scale from the camera's motion sensor, on a camera
path and a sensor whose answer is known."""

import math
import struct

import numpy as np

from iocean_reconstruct import scale


def _rot(axis, angle):
    return scale._rodrigues(np.asarray(axis, float) / np.linalg.norm(axis) * angle)


def _synthetic(true_scale=2.5, seconds=40.0, rate=200.0, every=0.5, seed=0):
    """A diver's camera finning along a transect: a slow swim, a fin-kick
    bob and sway, a gentle turning; the sensor turned against the camera."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, seconds, 1 / rate)
    pos = np.stack([0.3 * t, 0.15 * np.sin(2 * math.pi * 0.8 * t), 0.1 * np.sin(2 * math.pi * 1.1 * t + 1)], 1)
    yaw = 0.3 * np.sin(2 * math.pi * 0.05 * t)
    pitch = 0.1 * np.sin(2 * math.pi * 0.3 * t)
    rots = [_rot([0, 0, 1], y) @ _rot([0, 1, 0], p) for y, p in zip(yaw, pitch)]   # camera to world
    vel = np.gradient(pos, t, axis=0)
    acc = np.gradient(vel, t, axis=0)
    g = np.array([0, 0, -9.81])
    sensor_to_camera = _rot([1, 2, 3], 1.1)
    accel, gyro = [], []
    for k in range(len(t)):
        f_world = acc[k] - g
        f_cam = rots[k].T @ f_world
        accel.append(sensor_to_camera.T @ f_cam + rng.normal(0, 0.02, 3))
        nxt = rots[min(k + 1, len(t) - 1)]
        w_cam = scale._log(rots[k].T @ nxt) * rate
        gyro.append(sensor_to_camera.T @ w_cam + rng.normal(0, 0.002, 3))
    frames = []
    for k in range(0, len(t), int(rate * every)):
        frames.append((t[k], pos[k] / true_scale, rots[k]))
    return t, np.array(gyro), np.array(accel), frames, sensor_to_camera


def test_the_scale_comes_back_with_gravity_as_its_check():
    t, gyro, accel, frames, s2c = _synthetic()
    said = scale.align(frames, t, gyro, accel, s2c)
    assert abs(said["scale"] - 2.5) / 2.5 < 0.03
    assert abs(said["gravityMs2"] - 9.81) < 0.3


def test_the_sensors_turn_against_the_camera_is_found_from_the_gyroscope():
    t, gyro, accel, frames, s2c = _synthetic()
    pairs = []
    for (ti, _, ri), (tj, _, rj) in zip(frames, frames[1:]):
        rot, _, _ = scale.integrate(t, gyro, accel, ti, tj)
        pairs.append((scale._log(rot), scale._log(ri.T @ rj)))
    found = scale.camera_to_sensor(pairs)
    assert np.degrees(np.linalg.norm(scale._log(found.T @ s2c))) < 2.0


def test_gpmf_is_read_as_gopro_writes_it():
    def klv(key, kind, size, repeat, payload):
        pad = (-len(payload)) % 4
        return key.encode() + bytes([ord(kind), size]) + struct.pack(">H", repeat) + payload + b"\0" * pad

    accl = struct.pack(">hhh", 1000, -2000, 980) + struct.pack(">hhh", 1001, -2001, 981)
    strm = klv("SCAL", "s", 2, 1, struct.pack(">h", 100)) + klv("ACCL", "s", 6, 2, accl)
    devc = klv("STRM", "\0", 1, len(strm), strm)
    blob = klv("DEVC", "\0", 1, len(devc), devc)
    found = {}
    for *_, payload in scale._klv(blob):
        for *_, spayload in scale._klv(payload):
            for k, kk, sz, rp, pl in scale._klv(spayload):
                found[k] = scale._values(kk, sz, rp, pl)
    assert found["SCAL"] == 100
    assert np.allclose(found["ACCL"] / found["SCAL"], [[10.0, -20.0, 9.8], [10.01, -20.01, 9.81]])
