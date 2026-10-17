"""The tape painted out of every frame by LaMa (big-lama: simple-lama-inpainting,
its weights cached under TORCH_HOME). OpenCV's Telea left a smeared grey
stripe across textured reef; LaMa leaves reef. Then the pieces are trained on
these frames instead of the video's.

The tape painted out of every frame, under the
segmentation mask completed from the tape found in 3D, widened.
    lama_tape.py IMAGES MASKS OUT [SHEET_NAMES] [--only N,N]"""
import pathlib
import sys

import cv2
import numpy as np
import torch
from PIL import Image
from simple_lama_inpainting import SimpleLama

images, masks, out = (pathlib.Path(p) for p in sys.argv[1:4])
sheet = sys.argv[4].split(",") if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else []
only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
out.mkdir(parents=True, exist_ok=True)
lama = SimpleLama(device=torch.device("cuda"))
tiles, n = [], 0
for path in sorted(images.glob("*.jpg")):
    if only and path.stem not in only:
        continue
    img = Image.open(path).convert("RGB")
    m = cv2.imread(str(masks / f"{path.stem}.png"), cv2.IMREAD_GRAYSCALE)
    if m is not None and m.any():
        m = cv2.dilate((m > 127).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
        filled = lama(img, Image.fromarray(m)).crop((0, 0, img.width, img.height))
    else:
        filled = img
    filled.save(out / path.name, quality=97)
    n += 1
    if path.stem in sheet:
        tiles.append(np.hstack([np.asarray(img), np.asarray(filled)]))
if tiles:
    Image.fromarray(np.vstack(tiles)).resize((1280, 356 * len(tiles))).save(out.parent / "lama-sheet.jpg", quality=85)
print("inpainted", n)
