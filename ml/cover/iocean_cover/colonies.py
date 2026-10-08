"""Every coral colony a video shows, cut out and sorted by type.

A frame every `every` seconds is segmented (the model's 95 classes). With an
`outliner` (SAM 2, see outline.py) each colony is outlined on its own and named
by the class most of it is; without one, each connected patch of one class is
taken as a colony, which joins colonies of a kind that touch. Either way a
colony big enough and not cut by the frame's edge is one colony seen once: it
is cut out with its mask as a transparent PNG. The same colony is seen again a second later, a little moved;
a patch of the same class whose box overlaps one from the last few frames is
the same colony, and the sharper, larger view of the two is kept.

    colonies/<class>/<video>-<t>s-<n>.png   each colony, cut out
    catalog.json                            every colony: class, group, video,
                                            time, box, pixels, sharpness
    sheets/<class>.jpg                      the best of each class on one sheet
"""

from __future__ import annotations

import json
import pathlib
import re
import time

import numpy as np

# Coral and the other standing life a reef is built of; sand, rock, rubble,
# fish and water are not colonies.
WANTED_GROUPS = ("hard_coral", "soft_coral", "other_coral", "bleached_coral", "dead_coral", "other_life")


def _sharpness(gray: np.ndarray, mask: np.ndarray) -> float:
    """Variance of the Laplacian inside the mask: how much fine detail the view holds."""
    lap = (np.roll(gray, 1, 0) + np.roll(gray, -1, 0) + np.roll(gray, 1, 1) + np.roll(gray, -1, 1) - 4 * gray)
    inside = mask[1:-1, 1:-1]
    return float(lap[1:-1, 1:-1][inside].var()) if inside.any() else 0.0


def _iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _patches(classes: np.ndarray, wanted: set[int]):
    """Connected patches of one class: (mask, class id), for when there is no outliner."""
    from scipy import ndimage

    for c in sorted(set(np.unique(classes).tolist()) & wanted):
        labels, _ = ndimage.label(ndimage.binary_opening(classes == c, iterations=2))
        for k, box in enumerate(ndimage.find_objects(labels), start=1):
            if box is not None:
                mask = np.zeros(classes.shape, bool)
                mask[box] = labels[box] == k
                yield mask, c


def extract(segmenter, groups, videos: list[pathlib.Path], out: pathlib.Path, every: float = 1.0,
            min_pixels: int = 3000, edge: int = 3, remember: int = 3, iou: float = 0.3, outliner=None) -> dict:
    from PIL import Image
    from scipy import ndimage

    from .video import frames

    out.mkdir(parents=True, exist_ok=True)
    wanted = {i for i, label in segmenter.id2label.items()
              if groups.names[groups.lookup[i]] in WANTED_GROUPS}
    kept: dict[str, dict] = {}            # id -> record, the best view of each colony
    recent: list[list[tuple]] = []        # per recent frame: (class, box, id)
    t0, seen = time.time(), 0
    for video in videos:
        tag = video.stem
        recent.clear()
        for t, image in frames([video], every):
            classes = segmenter.classes(image)
            gray = image.mean(2).astype(np.float32)
            here = []
            found = ([(o["mask"], o["class"]) for o in outliner.colonies(image, classes, wanted)]
                     if outliner is not None else _patches(classes, wanted))
            for k, (whole, c) in enumerate(found, start=1):
                box = ndimage.find_objects(whole.astype(np.int8))[0]
                rows, cols = box
                one = whole[box]
                if one.sum() < min_pixels:
                    continue
                if (rows.start < edge or cols.start < edge or rows.stop > classes.shape[0] - edge
                        or cols.stop > classes.shape[1] - edge):
                    continue                          # cut by the frame: not the whole colony
                bbox = (cols.start, rows.start, cols.stop, rows.stop)
                sharp = _sharpness(gray[box], one)
                score = float(one.sum()) * np.sqrt(sharp)
                same = next((rid for frame in recent for (cc, bb, rid) in frame
                             if cc == c and _iou(bb, bbox) > iou and rid in kept), None)
                if same is not None and kept[same]["score"] >= score:
                    here.append((c, bbox, same))
                    continue
                rid = same or f"{tag}-{t:07.1f}s-{c}-{k}"
                label = segmenter.id2label[c]
                folder = out / "colonies" / _slug(label)
                folder.mkdir(parents=True, exist_ok=True)
                if same is not None:
                    (out / kept[same]["file"]).unlink(missing_ok=True)
                alpha = (ndimage.binary_dilation(one, iterations=1) * 255).astype(np.uint8)
                rgba = np.dstack([image[box], alpha])
                name = f"{tag}-{t:07.1f}s-{k}.png"
                Image.fromarray(rgba).save(folder / name)
                kept[rid] = {"id": rid, "class": label, "group": groups.names[groups.lookup[c]], "video": tag,
                             "t": round(t, 1), "box": list(map(int, bbox)), "pixels": int(one.sum()),
                             "sharpness": round(sharp, 1), "score": round(score, 1),
                             "file": f"colonies/{_slug(label)}/{name}"}
                here.append((c, bbox, rid))
            recent.append(here)
            del recent[:-remember]
            seen += 1
            if seen % 30 == 0:
                print(json.dumps({"frames": seen, "colonies": len(kept), "seconds": round(time.time() - t0)}),
                      flush=True)
    rows = sorted(kept.values(), key=lambda r: (r["class"], -r["score"]))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    said = {"videos": [str(v) for v in videos], "everySeconds": every, "frames": seen, "colonies": len(rows),
            "byClass": dict(sorted(counts.items(), key=lambda kv: -kv[1])), "minPixels": min_pixels,
            "seconds": round(time.time() - t0)}
    (out / "catalog.json").write_text(json.dumps({**said, "rows": rows}, indent=1) + "\n")
    sheets(out, rows)
    return said


def sheets(out: pathlib.Path, rows: list[dict], best: int = 40, cell: int = 220) -> None:
    """The best views of each class on one sheet, on grey so the cut-outs read."""
    from PIL import Image, ImageDraw

    (out / "sheets").mkdir(exist_ok=True)
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["class"], []).append(r)
    for label, these in by.items():
        these = sorted(these, key=lambda r: -r["score"])[:best]
        columns = 8
        sheet = Image.new("RGB", (columns * cell, ((len(these) + columns - 1) // columns) * cell + 30), (90, 90, 90))
        draw = ImageDraw.Draw(sheet)
        draw.text((6, 8), f"{label}: {len(by[label])} colonies, the best {len(these)}", fill=(255, 255, 255))
        for i, r in enumerate(these):
            img = Image.open(out / r["file"])
            img.thumbnail((cell - 8, cell - 8))
            x, y = (i % columns) * cell + 4, (i // columns) * cell + 34
            sheet.paste(img, (x, y), img)
        sheet.save(out / "sheets" / f"{_slug(label)}.jpg", quality=90)
