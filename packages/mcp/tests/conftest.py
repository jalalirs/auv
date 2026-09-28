"""Put the package itself on the path, so the tests import it the once.

Loading a module twice by file path gives two class objects with the same name,
and `except Refused` then does not catch the Refused a test raised — which is
not a subtlety worth living with in the tests for a server whose whole job is
to turn refusals into readable answers.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
