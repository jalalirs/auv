"""The reconstruction's scale, measured by the camera's own motion sensor.

A single video has no scale: the same frames come from a reef twice the size
filmed from twice as far. A GoPro also records what its accelerometer and
gyroscope felt (GPMF telemetry, in the MP4 beside the picture), and an
accelerometer reads metres per second squared. Between two frames, what it
felt, integrated, must equal how the reconstruction's camera moved, times the
scale, plus gravity and the velocity it already had. Over a hundred frame
pairs that is one linear least-squares problem in the scale, gravity and the
velocity at each frame: the alignment visual-inertial odometry starts from
(Qin, Li and Shen, VINS-Mono, IEEE T-RO 34:1004, 2018). Gravity comes out of
it unasked, and how close it lands to 9.81 m/s^2 is the check on the answer.

The sensor is not turned the way the camera is. That rotation is found from
the gyroscope: what it says the camera turned between two frames against
what the reconstruction says it turned (Kabsch on the rotation vectors).

GPMF is GoPro's documented format (github.com/gopro/gpmf-parser): a stream
of key, type, size, repeat, data, nested; read here directly.
"""

from __future__ import annotations

import math
import pathlib
import struct

import numpy as np

_TYPES = {"b": "b", "B": "B", "s": "h", "S": "H", "l": "i", "L": "I", "f": "f", "d": "d", "j": "q", "J": "Q"}


def _klv(data: bytes, start: int = 0, end: int | None = None):
    """Each (key, type, size, repeat, payload) at this level."""
    end = len(data) if end is None else end
    i = start
    while i + 8 <= end:
        key = data[i:i + 4].decode("latin-1")
        kind = chr(data[i + 4])
        size, repeat = data[i + 5], struct.unpack(">H", data[i + 6:i + 8])[0]
        length = size * repeat
        payload = data[i + 8:i + 8 + length]
        yield key, kind, size, repeat, payload
        i += 8 + ((length + 3) & ~3)


def _values(kind: str, size: int, repeat: int, payload: bytes) -> np.ndarray:
    code = _TYPES.get(kind)
    if code is None:
        return np.array([])
    width = struct.calcsize(code)
    per = size // width
    flat = np.array(struct.unpack(">" + code * (per * repeat), payload[:per * repeat * width]), dtype="float64")
    return flat.reshape(repeat, per) if per > 1 else flat


def telemetry(video: pathlib.Path) -> dict:
    """The accelerometer (m/s^2) and gyroscope (rad/s), each as (times, samples),
    in the sensor's own axes, timed by the packets they came in."""
    import av

    out = {"ACCL": ([], []), "GYRO": ([], [])}
    with av.open(str(video)) as container:
        stream = next(s for s in container.streams.data if "gpmd" in str(s.codec_context.codec_tag or "")
                      or s.metadata.get("handler_name", "").strip().startswith("GoPro MET"))
        base = float(stream.time_base)
        for packet in container.demux(stream):
            if packet.pts is None or packet.size == 0:
                continue
            t0, dt = packet.pts * base, (packet.duration or 0) * base
            blob = bytes(packet)
            for key, kind, _size, _repeat, payload in _klv(blob):
                if key != "DEVC" or kind != "\0":
                    continue
                for skey, _kind, _sz, _rp, spayload in _klv(payload):
                    if skey != "STRM":
                        continue
                    scale, found = None, {}
                    for k, kk, sz, rp, pl in _klv(spayload):
                        if k == "SCAL":
                            scale = _values(kk, sz, rp, pl)
                        elif k in ("ACCL", "GYRO"):
                            found[k] = _values(kk, sz, rp, pl)
                    for k, v in found.items():
                        if scale is not None and len(v):
                            v = v / (scale if np.ndim(scale) == 0 or len(np.atleast_1d(scale)) == 1
                                     else np.atleast_1d(scale)[None, :])
                            n = len(v)
                            out[k][0].extend(t0 + (np.arange(n) + 0.5) * dt / n)
                            out[k][1].extend(np.atleast_2d(v))
    return {k: (np.array(t), np.array(v)) for k, (t, v) in out.items()}


def _rodrigues(r: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(r))
    if angle < 1e-12:
        return np.eye(3)
    k = r / angle
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(angle) * kx + (1 - math.cos(angle)) * kx @ kx


def _log(rotation: np.ndarray) -> np.ndarray:
    angle = math.acos(max(-1.0, min(1.0, (np.trace(rotation) - 1) / 2)))
    if angle < 1e-9:
        return np.zeros(3)
    return angle / (2 * math.sin(angle)) * np.array([rotation[2, 1] - rotation[1, 2],
                                                     rotation[0, 2] - rotation[2, 0],
                                                     rotation[1, 0] - rotation[0, 1]])


def integrate(times: np.ndarray, gyro: np.ndarray, accel: np.ndarray, t0: float, t1: float):
    """Between t0 and t1, in the sensor's frame at t0: the rotation it turned
    through, and the specific force integrated once (beta) and twice (alpha)."""
    inside = (times >= t0) & (times < t1)
    rot, alpha, beta = np.eye(3), np.zeros(3), np.zeros(3)
    ts = np.concatenate([[t0], times[inside], [t1]])
    gs = np.concatenate([gyro[inside][:1] if inside.any() else np.zeros((1, 3)), gyro[inside],
                         gyro[inside][-1:] if inside.any() else np.zeros((1, 3))])
    acs = np.concatenate([accel[inside][:1] if inside.any() else np.zeros((1, 3)), accel[inside],
                          accel[inside][-1:] if inside.any() else np.zeros((1, 3))])
    for k in range(len(ts) - 1):
        dt = ts[k + 1] - ts[k]
        a = rot @ acs[k]
        alpha += beta * dt + 0.5 * a * dt * dt
        beta += a * dt
        rot = rot @ _rodrigues(gs[k] * dt)
    return rot, alpha, beta


def camera_to_sensor(pairs: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """The rotation taking the sensor's axes to the camera's, from pairs of
    (rotation vector the gyroscope says, rotation vector the camera says)."""
    g = np.array([p[0] for p in pairs])
    c = np.array([p[1] for p in pairs])
    u, _, vt = np.linalg.svd(g.T @ c)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    return vt.T @ np.diag([1, 1, d]) @ u.T


def align(frames: list[tuple[float, np.ndarray, np.ndarray]], times, gyro, accel,
          sensor_to_camera: np.ndarray, gap: float = 0.75) -> dict:
    """Scale, gravity and velocities from frames (time, camera centre in model
    units, camera-to-model rotation) and the sensor, by linear least squares."""
    n = len(frames)
    rows, rhs = [], []
    unknowns = 1 + 3 + 3 * n
    for i in range(n - 1):
        (ti, pi, ri), (tj, pj, _rj) = frames[i], frames[i + 1]
        dt = tj - ti
        if dt <= 0 or dt > gap:
            continue
        _, alpha, beta = integrate(times, gyro, accel, ti, tj)
        world_alpha = ri @ (sensor_to_camera @ alpha)
        world_beta = ri @ (sensor_to_camera @ beta)
        for axis in range(3):
            # s (p_j - p_i) - v_i dt - 1/2 g dt^2 = R alpha
            row = np.zeros(unknowns)
            row[0] = pj[axis] - pi[axis]
            row[1 + axis] = -0.5 * dt * dt
            row[4 + 3 * i + axis] = -dt
            rows.append(row)
            rhs.append(world_alpha[axis])
            # v_j - v_i - g dt = R beta
            row = np.zeros(unknowns)
            row[4 + 3 * (i + 1) + axis] = 1.0
            row[4 + 3 * i + axis] = -1.0
            row[1 + axis] = -dt
            rows.append(row)
            rhs.append(world_beta[axis])
    a, b = np.array(rows), np.array(rhs)
    used = np.abs(a).sum(0) > 0
    x = np.zeros(unknowns)
    x[used], *_ = np.linalg.lstsq(a[:, used], b, rcond=None)
    residual = float(np.sqrt(np.mean((a @ x - b) ** 2)))
    return {"scale": float(x[0]), "gravity": x[1:4].tolist(), "gravityMs2": float(np.linalg.norm(x[1:4])),
            "pairs": len(rows) // 6, "residualM": residual}


def clock_offset(times, gyro, frames, search: float = 0.5, step: float = 0.01) -> float:
    """How far the sensor's clock is from the frames', by matching how fast the
    gyroscope says the camera turned with how fast the reconstruction says."""
    rates_t, rates = [], []
    for (ti, _, ri), (tj, _, rj) in zip(frames, frames[1:]):
        if 0 < tj - ti < 0.75:
            rates_t.append((ti + tj) / 2)
            rates.append(np.linalg.norm(_log(ri.T @ rj)) / (tj - ti))
    rates_t, rates = np.array(rates_t), np.array(rates)
    speed = np.linalg.norm(gyro, axis=1)
    best, best_score = 0.0, -np.inf
    for off in np.arange(-search, search + step / 2, step):
        felt = np.interp(rates_t, times - off, speed)
        if felt.std() == 0 or rates.std() == 0:
            continue
        score = np.corrcoef(felt, rates)[0, 1]
        if score > best_score:
            best, best_score = float(off), float(score)
    return best


def measure(video: pathlib.Path, text: pathlib.Path, start_s: float, every_s: float) -> dict:
    """The reconstruction's scale in metres per model unit, from the video's
    own telemetry, with what it rests on."""
    sensor = telemetry(video)
    (ta, accel), (tg, gyro) = sensor["ACCL"], sensor["GYRO"]
    if not len(ta) or not len(tg):
        return {"measured": False, "why": "the video carries no accelerometer or gyroscope"}
    accel_on_gyro = np.stack([np.interp(tg, ta, accel[:, k]) for k in range(3)], axis=1)
    frames = []
    lines = [ln for ln in (text / "images.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    for line in lines[::2]:
        p = line.split()
        qw, qx, qy, qz, tx, ty, tz = (float(v) for v in p[1:8])
        r = np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                      [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                      [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])
        t = start_s + int(pathlib.Path(p[9]).stem) * every_s
        frames.append((t, -r.T @ np.array([tx, ty, tz]), r.T))
    frames.sort(key=lambda f: f[0])
    offset = clock_offset(tg, gyro, frames)
    tg = tg - offset
    pairs = []
    for (ti, _, ri), (tj, _, rj) in zip(frames, frames[1:]):
        if 0 < tj - ti < 0.75:
            rot, _, _ = integrate(tg, gyro, accel_on_gyro, ti, tj)
            seen = _log(ri.T @ rj)
            if np.linalg.norm(seen) > math.radians(1.0):
                pairs.append((_log(rot), seen))
    turn = camera_to_sensor(pairs)
    agree = float(np.mean([np.degrees(np.linalg.norm(turn @ g - c)) for g, c in pairs]))
    said = align(frames, tg, gyro, accel_on_gyro, turn)
    return {"measured": True, **said, "clockOffsetS": offset, "turnPairs": len(pairs),
            "turnDisagreesDeg": agree, "frames": len(frames),
            "how": "the video's own accelerometer and gyroscope (GoPro GPMF), aligned with the reconstruction's "
                   "camera path by linear least squares (VINS-Mono's initialisation); gravity solved for, and its "
                   "magnitude is the check"}
