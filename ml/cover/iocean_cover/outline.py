"""One outline per colony: SAM 2.1 draws them, the segmentation names them.

The segmentation says what each pixel is, so two Porites touching are one
patch of "porites alive" to it. SAM 2 draws objects. It is prompted with a
point every `point_spacing` pixels on whatever the segmentation called coral
(or other standing life); for each point it offers three outlines, from a part
to the whole. The largest of the three that is mostly one class (`min_purity`)
and that SAM itself rates well (`min_score`) is that point's colony. Points on
the same colony give the same outline again, so outlines are taken best first
and one that overlaps a kept one by `overlap` of the smaller is dropped.
"""

from __future__ import annotations

import pathlib

import numpy as np


class Outliner:
    def __init__(self, folder: str | pathlib.Path, device: str | None = None, point_spacing: int = 48,
                 min_score: float = 0.8, min_purity: float = 0.6, overlap: float = 0.5, chunk: int = 64) -> None:
        import torch
        from transformers import Sam2Model, Sam2Processor

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = Sam2Model.from_pretrained(folder).to(self.device).eval()
        self.processor = Sam2Processor.from_pretrained(folder)
        self.spacing, self.min_score, self.min_purity = point_spacing, min_score, min_purity
        self.overlap, self.chunk = overlap, chunk

    def points(self, wanted: np.ndarray) -> np.ndarray:
        """Prompt points on a grid, kept where the ground is wanted and a few
        pixels in from its edge, so a point is on a colony and not its rim."""
        from scipy import ndimage

        inside = ndimage.binary_erosion(wanted, iterations=4)
        s = self.spacing
        rows, cols = np.mgrid[s // 2:wanted.shape[0]:s, s // 2:wanted.shape[1]:s]
        keep = inside[rows, cols]
        return np.column_stack([cols[keep], rows[keep]]).astype(np.float32)

    def colonies(self, image: np.ndarray, classes: np.ndarray, wanted_ids: set[int]) -> list[dict]:
        """Each colony: its mask (full size, bool), class id, purity and SAM's score."""
        import torch
        import torch.nn.functional as F

        wanted = np.isin(classes, list(wanted_ids))
        pts = self.points(wanted)
        if not len(pts):
            return []
        present = sorted(set(np.unique(classes[wanted]).tolist()))
        h, w = classes.shape
        # The class maps at half size, for counting what each outline is made of.
        cls = torch.from_numpy(classes.astype(np.int64)).to(self.device)
        onehot = torch.stack([(cls == c) for c in present]).float()
        onehot = F.avg_pool2d(onehot[None], 2)[0].flatten(1)                     # (K, HW/4)
        with torch.no_grad():
            enc = self.processor(images=image, return_tensors="pt").to(self.device)
            emb = self.model.get_image_embeddings(enc["pixel_values"])
            candidates = []
            for i in range(0, len(pts), self.chunk):
                part = pts[i:i + self.chunk]
                inp = self.processor(images=image, input_points=[[[[float(x), float(y)]] for x, y in part]],
                                     input_labels=[[[1]] * len(part)], return_tensors="pt").to(self.device)
                out = self.model(input_points=inp["input_points"], input_labels=inp["input_labels"],
                                 image_embeddings=emb, multimask_output=True)
                masks = self.processor.post_process_masks(out.pred_masks, inp["original_sizes"])[0]  # (n, 3, h, w)
                scores = out.iou_scores[0]                                                          # (n, 3)
                small = F.avg_pool2d(masks.float().flatten(0, 1)[:, None], 2)[:, 0].flatten(1)      # (n*3, HW/4)
                area = small.sum(1)
                counts = small @ onehot.T                                                           # (n*3, K)
                purity, which = (counts / area.clamp_min(1)[:, None]).max(1)
                purity, which = purity.view(-1, 3), which.view(-1, 3)
                area3 = area.view(-1, 3)
                for j in range(len(part)):
                    good = (scores[j] >= self.min_score) & (purity[j] >= self.min_purity) & (area3[j] > 0)
                    if not good.any():
                        continue
                    k = int(torch.where(good, area3[j], torch.full_like(area3[j], -1)).argmax())
                    candidates.append({"mask": masks[j, k], "small": small.view(-1, 3, small.shape[-1])[j, k] > 0.5,
                                       "class": present[int(which[j, k])], "purity": float(purity[j, k]),
                                       "score": float(scores[j, k]), "area": float(area3[j, k])})
        # Best first: SAM's score, then size; an outline mostly inside a kept one is that one.
        candidates.sort(key=lambda c: (-round(c["score"], 2), -c["area"]))
        kept: list[dict] = []
        for c in candidates:
            if any(float((c["small"] & k["small"]).sum()) > self.overlap * min(c["area"], k["area"]) for k in kept):
                continue
            kept.append(c)
        return [{"mask": k["mask"].cpu().numpy(), "class": k["class"], "purity": k["purity"], "score": k["score"]}
                for k in kept]
