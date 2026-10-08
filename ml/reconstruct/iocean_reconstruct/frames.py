"""Frames from a dive video, for structure from motion.

A frame every `every` seconds between `start` and `end`, scaled so the longest
side is `longest_side` pixels. Videos given one after the other are one
transect, as a GoPro cuts a long one into files. Each frame is written as a
JPEG named by its order, which is the order COLMAP's sequential matcher reads.
"""

from __future__ import annotations

import json
import pathlib


def extract(paths: list[pathlib.Path], into: pathlib.Path, every: float, start: float = 0.0,
            end: float | None = None, longest_side: int = 1600) -> dict:
    import av

    into.mkdir(parents=True, exist_ok=True)
    offset, wanted, n, size = 0.0, start, 0, None
    for path in paths:
        with av.open(str(path)) as box:
            stream = box.streams.video[0]
            stream.thread_type = "AUTO"
            length = float(stream.duration * stream.time_base) if stream.duration else float(box.duration / 1e6)
            for frame in box.decode(stream):
                t = offset + float(frame.pts * stream.time_base)
                if end is not None and t > end:
                    break
                if t + 1e-6 < wanted:
                    continue
                k = longest_side / max(frame.width, frame.height)
                w, h = int(round(frame.width * k / 2)) * 2, int(round(frame.height * k / 2)) * 2
                frame.to_image(width=w, height=h).save(into / f"{n:05d}.jpg", quality=95)
                size, n, wanted = (w, h), n + 1, wanted + every
        offset += length
        if end is not None and offset > end:
            break
    said = {"videos": [str(p) for p in paths], "fromSeconds": start, "toSeconds": end, "everySeconds": every,
            "frames": n, "size": size}
    (into / "frames.json").write_text(json.dumps(said, indent=1) + "\n")
    return said
