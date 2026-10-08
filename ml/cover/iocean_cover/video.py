"""Cover along a video transect.

How reef teams in the Red Sea survey: a diver (or a vehicle) swims a transect
with a GoPro a metre or two above the reef, from a start to an end it marks.
That is the model's own ground: CoralscapesV2 is frames of exactly such videos,
and its check is per frame. So a video becomes cover the simple way: a frame
every `every` seconds, each segmented, each frame's groups counted over its
seabed pixels, as a point count would.

    frames.csv     one row a frame: its time, where it was if the transect's
                   ends were given (straight between them, at an even pace, as
                   a diver swims a tape), how much of it is seabed, and each
                   group's share of that seabed
    transect.json  the transect's cover (each frame weighted by its seabed),
                   the model and its check, the video and the settings
    frames.png     a few frames and what the model said of them, to look at

A frame that is mostly water (the diver looking up, the start of a dive) says
little about the bottom: frames with less than `min_seabed` seabed are kept in
frames.csv and left out of the transect's cover.
"""

from __future__ import annotations

import csv
import json
import math
import pathlib
import time

import numpy as np


def frames(paths: list[pathlib.Path], every: float, start: float = 0.0, end: float | None = None,
           shorter: int = 1024):
    """(seconds from the start of the first video, RGB frame) every `every`
    seconds between `start` and `end`; videos one after the other, as a GoPro
    cuts a long transect into files. Frames are scaled so their shorter side is
    `shorter` pixels, the scale the model was trained at."""
    import av

    offset, wanted = 0.0, start
    for path in paths:
        with av.open(str(path)) as box:
            stream = box.streams.video[0]
            stream.thread_type = "AUTO"
            length = float(stream.duration * stream.time_base) if stream.duration else float(box.duration / 1e6)
            for frame in box.decode(stream):
                t = offset + float(frame.pts * stream.time_base)
                if end is not None and t > end:
                    return
                if t + 1e-6 < wanted:
                    continue
                w, h = frame.width, frame.height
                k = shorter / min(w, h)
                image = frame.to_ndarray(format="rgb24", width=int(round(w * k / 2)) * 2,
                                         height=int(round(h * k / 2)) * 2)
                yield t, image
                wanted += every
        offset += length


def _place(t: float, t0: float, t1: float, a: tuple[float, float] | None, b: tuple[float, float] | None):
    if a is None or b is None or t1 <= t0:
        return None
    f = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
    return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])


def transect(segmenter, groups, paths: list[pathlib.Path], out: pathlib.Path, about: dict, every: float = 1.0,
             start: float = 0.0, end: float | None = None, begin: tuple[float, float] | None = None,
             finish: tuple[float, float] | None = None, min_seabed: float = 0.3) -> dict:
    from PIL import Image

    from .mosaic import COLOURS

    out.mkdir(parents=True, exist_ok=True)
    names = list(groups.seabed)
    not_seabed = groups.names.index("not_seabed")
    palette = np.array([COLOURS.get(n, (255, 255, 255)) for n in groups.names], np.uint8)
    rows, shown, t0 = [], [], time.time()
    total = np.zeros(len(names))
    weight = 0.0
    last = end
    for t, image in frames(paths, every, start, end):
        classes = segmenter.classes(image)
        g = groups.of(classes)
        seabed = float((g != not_seabed).mean())
        shares = groups.shares(classes) or {n: 0.0 for n in names}
        rows.append({"t": round(t, 2), "seabed": round(seabed, 4), **{n: round(shares[n], 4) for n in names}})
        if seabed >= min_seabed:
            total += seabed * np.array([shares[n] for n in names])
            weight += seabed
        if len(rows) % 15 == 1 and len(shown) < 6:
            small = Image.fromarray(np.concatenate([image, palette[g]], 1))
            small.thumbnail((1600, 400))
            shown.append(np.asarray(small))
        if len(rows) % 30 == 0:
            print(json.dumps({"frames": len(rows), "t": round(t), "seconds": round(time.time() - t0)}), flush=True)
        last = t
    if not rows:
        raise ValueError("no frames between the times given")
    t_end = end if end is not None else last
    for r in rows:
        where = _place(r["t"], start, t_end, begin, finish)
        if where:
            r["latitude"], r["longitude"] = round(where[0], 7), round(where[1], 7)
    with open(out / "frames.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    used = sum(1 for r in rows if r["seabed"] >= min_seabed)
    length = None
    if begin and finish:
        north = (finish[0] - begin[0]) * 111_320.0
        east = (finish[1] - begin[1]) * 111_320.0 * math.cos(math.radians((begin[0] + finish[0]) / 2))
        length = round(math.hypot(north, east), 1)
    said = {
        **about, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0),
        "videos": [str(p) for p in paths], "fromSeconds": start, "toSeconds": round(t_end, 2), "everySeconds": every,
        "frames": len(rows), "framesUsed": used, "minSeabed": min_seabed,
        "begin": list(begin) if begin else None, "end": list(finish) if finish else None, "lengthM": length,
        "cover": {n: round(float(total[k] / weight), 4) for k, n in enumerate(names)} if weight else None,
    }
    (out / "transect.json").write_text(json.dumps(said, indent=1) + "\n")
    if shown:
        width = max(s.shape[1] for s in shown)
        Image.fromarray(np.concatenate([np.pad(s, ((0, 4), (0, width - s.shape[1]), (0, 0))) for s in shown])).save(
            out / "frames.png")
    return said
