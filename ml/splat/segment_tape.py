"""The survey tape in every frame (step 1 of taking it out of a reef trained
on a dive video; then masks_from_splats.py, lama_tape.py, and train the
pieces on the painted frames). Run inside iocean/3dgrut with transformers
installed; MODEL_DIR is CoralscapesV2's SegFormer.

The survey tape in every frame, by CoralscapesV2's own classes ('transect
line', 'transect tools'): a mask per frame, and a sheet of a few.
    segment_tape.py MODEL_DIR IMAGES OUT_DIR [NAME,NAME,... for the sheet] [--only N,N,...]"""
import json
import pathlib
import sys

import numpy as np
import torch
from PIL import Image
from transformers import SegformerForSemanticSegmentation

model_dir, images, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
sheet_names = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []
only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
out.mkdir(parents=True, exist_ok=True)
model = SegformerForSemanticSegmentation.from_pretrained(model_dir).cuda().eval().half()
id2label = model.config.id2label
tape_ids = [int(i) for i, name in id2label.items() if name in ("transect line", "transect tools")]
pre = json.loads((model_dir / "preprocessor_config.json").read_text())
mean = torch.tensor(pre.get("image_mean", [0.485, 0.456, 0.406])).view(1, 3, 1, 1).cuda().half()
std = torch.tensor(pre.get("image_std", [0.229, 0.224, 0.225])).view(1, 3, 1, 1).cuda().half()
names = sorted(p.stem for p in images.glob("*.jpg"))
if only:
    names = [n for n in names if n in only]
counts, tiles = {}, []
with torch.no_grad():
    for name in names:
        rgb = Image.open(images / f"{name}.jpg").convert("RGB")
        W, H = rgb.size
        # The model was trained at 1024 by 1024; the frame at 1024 wide keeps its
        # thin tape a few pixels across.
        x = torch.from_numpy(np.asarray(rgb.resize((1024, int(1024 * H / W / 32 + 0.5) * 32)), dtype=np.float32) / 255.0)
        x = x.permute(2, 0, 1)[None].cuda().half()
        logits = model(pixel_values=(x - mean) / std).logits
        logits = torch.nn.functional.interpolate(logits.float(), size=(H, W), mode="bilinear", align_corners=False)
        label = logits.argmax(1)[0]
        mask = torch.zeros_like(label, dtype=torch.bool)
        for t in tape_ids:
            mask |= label == t
        m = mask.cpu().numpy()
        Image.fromarray((m * 255).astype(np.uint8)).save(out / f"{name}.png")
        counts[name] = int(m.sum())
        if name in sheet_names:
            a = np.asarray(rgb).copy()
            b = a.copy()
            b[m] = (255, 0, 0)
            tiles.append(np.hstack([a, b]))
if tiles:
    Image.fromarray(np.vstack(tiles)).resize((1280, 360 * len(tiles))).save(out / "_sheet.jpg", quality=85)
print(json.dumps({"frames": len(counts), "tapeIds": tape_ids,
                  "withTape": sum(1 for v in counts.values() if v > 200),
                  "medianTapePx": int(np.median([v for v in counts.values()])) if counts else 0}))
