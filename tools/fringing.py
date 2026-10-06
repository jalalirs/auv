"""The constructed fringing reef lives in the places module now
(packages/places/iocean_places/sources/fringing.py); make-site --build and the
tests import it from here."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "places"))

from iocean_places.sources.fringing import build  # noqa: E402,F401
