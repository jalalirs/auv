"""The Sentinel-2 band reader lives in the places module (iocean_places.fetch.sentinel_bands),
so the depth model and the places that use it read the satellite the same way."""

from iocean_places.fetch.sentinel_bands import *  # noqa: F403
from iocean_places.fetch.sentinel_bands import BANDS, COLLECTION, GDAL_ENV, MASKED, clear_scenes, stack, use_gdal_env  # noqa: F401
