"""Run the segmentation model over an image of any size.

The model was trained on 1024-pixel crops, so a larger image is cut into
1024-pixel windows that overlap by a quarter, and their class probabilities
are blended with a taper (1 in a window's middle, near 0 at its edges), so no
window's edge shows in the result. A smaller image is padded by reflection.

Probabilities can be gathered into groups as they are blended (`into`), which
is what a photo mosaic needs: 95 classes over a 4,000-pixel block would not
fit on the GPU, fourteen groups do.

`allowed` rules classes out before the probabilities are taken. A photo
mosaic looks straight down at the seabed and every imaged pixel of it is
seabed; the model, trained on a diver's view across a reef, otherwise calls a
hazy patch of it open water.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np


def _taper(n: int):
    import torch

    ramp = torch.sin(torch.linspace(0, np.pi, n)) ** 2 + 1e-3
    return torch.outer(ramp, ramp)


def _starts(size: int, window: int, stride: int) -> list[int]:
    """Window starts that cover 0..size, the last flush with the end."""
    if size <= window:
        return [0]
    starts = list(range(0, size - window, stride))
    return starts + [size - window]


class Segmenter:
    def __init__(self, folder: str | pathlib.Path, device: str | None = None, window: int = 1024,
                 stride: int = 768, batch: int = 4) -> None:
        import torch
        from transformers import SegformerForSemanticSegmentation

        folder = pathlib.Path(folder)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SegformerForSemanticSegmentation.from_pretrained(folder).to(self.device).eval()
        pre = json.loads((folder / "preprocessor_config.json").read_text())
        self.mean = torch.tensor(pre["image_mean"], device=self.device)[:, None, None]
        self.std = torch.tensor(pre["image_std"], device=self.device)[:, None, None]
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}
        self.window, self.stride, self.batch = window, stride, batch

    def probabilities(self, image: np.ndarray, into: np.ndarray | None = None, allowed: np.ndarray | None = None):
        """Blended probabilities, (classes or groups, rows, columns), as a
        tensor on the model's device. `image` is (rows, columns, 3) uint8;
        `into` is a (groups, classes) 0/1 matrix to gather classes into groups;
        `allowed` a boolean per class, False for the ones ruled out."""
        import torch
        import torch.nn.functional as F

        rows, cols = image.shape[:2]
        w = self.window
        x = torch.from_numpy(np.ascontiguousarray(image)).to(self.device).permute(2, 0, 1).float() / 255.0
        x = (x - self.mean) / self.std
        pr, pc = max(0, w - rows), max(0, w - cols)
        if pr or pc:
            x = F.pad(x[None], (0, pc, 0, pr), mode="reflect" if pr < rows and pc < cols else "replicate")[0]
        R, C = x.shape[1:]
        gather = None if into is None else torch.from_numpy(into.astype("float32")).to(self.device)
        ruled_out = None if allowed is None else torch.from_numpy(~np.asarray(allowed, bool)).to(self.device)
        k = len(self.id2label) if gather is None else gather.shape[0]
        out = torch.zeros((k, R, C), device=self.device)
        weight = torch.zeros((R, C), device=self.device)
        taper = _taper(w).to(self.device)
        spots = [(r, c) for r in _starts(R, w, self.stride) for c in _starts(C, w, self.stride)]
        with torch.no_grad():
            for i in range(0, len(spots), self.batch):
                part = spots[i:i + self.batch]
                xb = torch.stack([x[:, r:r + w, c:c + w] for r, c in part])
                with torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
                    logits = self.model(pixel_values=xb).logits
                logits = logits.float()
                if ruled_out is not None:
                    logits[:, ruled_out] = -1e4
                p = F.interpolate(logits, size=(w, w), mode="bilinear", align_corners=False).softmax(1)
                if gather is not None:
                    p = torch.einsum("gc,bchw->bghw", gather, p)
                for (r, c), one in zip(part, p):
                    out[:, r:r + w, c:c + w] += one * taper
                    weight[r:r + w, c:c + w] += taper
        return (out / weight)[:, :rows, :cols]

    def classes(self, image: np.ndarray, allowed: np.ndarray | None = None) -> np.ndarray:
        """The most likely class id at every pixel."""
        return self.probabilities(image, allowed=allowed).argmax(0).to("cpu").numpy().astype(np.int16)


def stretch(rgb: np.ndarray, valid: np.ndarray, low: float = 0.5, high: float = 99.5) -> np.ndarray:
    """Each channel stretched so its `low` and `high` percentiles over the
    imaged pixels span 0 to 255, as USGS stretched each SQUID-5 photo before
    the mosaic: the deeper parts of a mosaic come out hazy and flat, and the
    model was trained on a diver's camera, close and in contrast."""
    if not valid.any():
        return rgb
    out = np.empty_like(rgb)
    for c in range(3):
        lo, hi = np.percentile(rgb[..., c][valid], [low, high])
        out[..., c] = np.clip((rgb[..., c].astype(np.float32) - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)
    return out


def seabed_only(groups, id2label: dict[int, str]) -> np.ndarray:
    """Allowed classes when everything imaged is seabed: all but those in not_seabed."""
    size = max(id2label) + 1
    return np.array([groups.names[groups.lookup[i]] != "not_seabed" for i in range(size)])


def gather_matrix(groups, id2label: dict[int, str]) -> np.ndarray:
    """(groups, classes) 0/1 matrix: which group each of the model's outputs falls in."""
    size = max(id2label) + 1
    m = np.zeros((len(groups.names), size), dtype=np.float32)
    for i in range(size):
        m[groups.lookup[i] if i < len(groups.lookup) else groups.names.index("not_seabed"), i] = 1.0
    return m
