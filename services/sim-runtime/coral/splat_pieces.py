"""Which piece of a video-trained reef to draw, for where the camera is.

A dive video too long for one set of splats is trained in overlapping pieces
(ml/splat), each from its own stretch of the swim. A piece is right from its
own stretch and wrong from the others: the reef ahead of the middle piece's
last frames is also the reef under the last piece's first ones, and the last
piece only ever saw it close and from above. Joined into one set, those
splats came out as dark shapes over the far reef in 49 of 756 frames, where
each piece alone drew its own frames clean.

So a place keeps every piece whole and draws one: the piece whose stretch of
the swim passes nearest the camera. A camera near the boundary between two
stretches would flip between them, so the piece already drawn is kept until
another is nearer by `margin` metres.

site.json: reef.splats.pieces = [{"prim": "Part0", "frames": [1, 260],
"path": [[x, y, z], ...]}, ...], the path in the place's metres.
"""

from __future__ import annotations

import numpy as np


class Pieces:
    def __init__(self, pieces: list[dict], margin: float = 0.75):
        self.prims = [str(p["prim"]) for p in pieces]
        self.paths = [np.asarray(p["path"], dtype=float).reshape(-1, 3) for p in pieces]
        self.margin = float(margin)
        self.drawn: int | None = None

    def distances(self, eye) -> np.ndarray:
        eye = np.asarray(eye, dtype=float)
        return np.array([np.linalg.norm(path - eye, axis=1).min() if len(path) else np.inf
                         for path in self.paths])

    def which(self, eye) -> int:
        """The piece to draw from `eye`, holding the one drawn near a boundary."""
        d = self.distances(eye)
        best = int(np.argmin(d))
        if self.drawn is None or d[best] + self.margin < d[self.drawn]:
            self.drawn = best
        return self.drawn


def pieces_of(site: dict) -> Pieces | None:
    """The place's pieces, or None when its reef is not drawn in pieces."""
    pieces = (((site or {}).get("reef") or {}).get("splats") or {}).get("pieces") or []
    return Pieces(pieces) if len(pieces) > 1 else None
