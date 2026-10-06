"""iOcean places: build a place from whatever data there is.

    sources -> layers -> fusion -> place -> scene

See docs/plan/r8.md. `python -m iocean_places build recipe.json --into DIR`.
"""

from .build import build, layers_of
from .fusion import fuse
from .grid import Grid
from .layer import Layer, Provenance
from .recipe import Recipe

__all__ = ["Grid", "Layer", "Provenance", "Recipe", "build", "fuse", "layers_of"]
