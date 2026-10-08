"""Check the model on CoralscapesV2's test split: 473 frames from five dive
sites it never saw.

Two kinds of score:

- pixels: accuracy and mean IoU over the 95 classes (what the model's card
  reports, so the run can be held against it), and IoU per cover group;
- cover: for every frame, each group's share of the seabed as the model says
  it and as the annotators drew it. This is the number a cover map stands on:
  a model can outline a colony badly and still get its share right, or the
  other way round.
"""

from __future__ import annotations

import io
import json
import pathlib
import time

import numpy as np


def frames(folder: pathlib.Path, limit: int | None = None):
    """(image, label) for every frame of the test parquet files in `folder`."""
    import pyarrow.parquet as pq
    from PIL import Image

    n = 0
    for path in sorted(folder.glob("data/test-*.parquet")):
        table = pq.ParquetFile(path)
        for batch in table.iter_batches(batch_size=8, columns=["image", "label"]):
            for image, label in zip(batch.column("image").to_pylist(), batch.column("label").to_pylist()):
                yield (np.asarray(Image.open(io.BytesIO(image["bytes"])).convert("RGB")),
                       np.asarray(Image.open(io.BytesIO(label["bytes"]))).astype(np.int16))
                n += 1
                if limit and n >= limit:
                    return


def _iou(confusion: np.ndarray) -> np.ndarray:
    tp = np.diag(confusion).astype("float64")
    union = confusion.sum(0) + confusion.sum(1) - tp
    return np.where(union > 0, tp / np.maximum(union, 1), np.nan)


def evaluate(segmenter, groups, test: pathlib.Path, out: pathlib.Path, limit: int | None = None) -> dict:
    size = max(segmenter.id2label) + 1
    G = len(groups.names)
    confusion = np.zeros((size, size), dtype=np.int64)
    gconf = np.zeros((G, G), dtype=np.int64)
    rows, t0 = [], time.time()
    for k, (image, label) in enumerate(frames(test, limit)):
        pred = segmenter.classes(image)
        known = label > 0
        confusion += np.bincount(label[known] * size + pred[known], minlength=size * size).reshape(size, size)
        gl, gp = groups.of(label[known]), groups.of(pred[known])
        gconf += np.bincount(gl * G + gp, minlength=G * G).reshape(G, G)
        drawn, said = groups.shares(label, known), groups.shares(pred, known)
        if drawn and said:
            rows.append({"frame": k, "drawn": drawn, "said": said})
        if k % 50 == 0:
            print(json.dumps({"frame": k, "seconds": round(time.time() - t0)}), flush=True)

    iou = _iou(confusion)[1:]
    present = confusion.sum(1)[1:] > 0
    giou = _iou(gconf)
    cover = {}
    for name in groups.seabed:
        d = np.array([r["drawn"][name] for r in rows])
        s = np.array([r["said"][name] for r in rows])
        cover[name] = {
            "meanDrawn": round(float(d.mean()), 4), "meanSaid": round(float(s.mean()), 4),
            "meanAbsError": round(float(np.abs(s - d).mean()), 4), "bias": round(float((s - d).mean()), 4),
            "correlation": round(float(np.corrcoef(d, s)[0, 1]), 3) if d.std() > 0 and s.std() > 0 else None}
    report = {
        "frames": len(rows), "seconds": round(time.time() - t0),
        "pixelAccuracy": round(float(np.diag(confusion)[1:].sum() / confusion[1:].sum()), 4),
        "meanIoU": round(float(np.nanmean(iou[present])), 4),
        "groupIoU": {n: (None if np.isnan(v) else round(float(v), 4)) for n, v in zip(groups.names, giou)},
        "cover": cover,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({**report, "perFrame": rows}, indent=1) + "\n")
    (out / "report.md").write_text(markdown(report))
    return report


def markdown(r: dict) -> str:
    lines = [f"# The model on CoralscapesV2's test split ({r['frames']} frames, five dive sites it never saw)", "",
             f"Pixel accuracy {r['pixelAccuracy']:.1%}, mean IoU over 95 classes {r['meanIoU']:.1%}.", "",
             "| group | IoU | seabed share drawn | said | mean error per frame | bias | correlation |",
             "|---|---|---|---|---|---|---|"]
    for name, c in r["cover"].items():
        iou = r["groupIoU"].get(name)
        lines.append(f"| {name} | {'' if iou is None else f'{iou:.0%}'} | {c['meanDrawn']:.1%} | {c['meanSaid']:.1%} | "
                     f"{c['meanAbsError']:.1%} | {c['bias']:+.1%} | {c['correlation']} |")
    return "\n".join(lines) + "\n"
