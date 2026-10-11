"""A lamp's place in the stage is a valid prim path whatever the package calls it."""

import re

from runner import lamp_path


def test_a_hyphenated_lamp_name_still_makes_a_prim_path():
    # The BlueROV2 Heavy's lamps are "port-fore" and the like; a hyphen in a
    # prim name made every dive in it fail as the lamps were hung.
    for name in ("port-fore", "starboard aft", "lamp.1", "Lumen"):
        path = lamp_path(name)
        assert re.fullmatch(r"/World/Lamp_[A-Za-z0-9_]+", path), path
    assert lamp_path("port-fore") != lamp_path("starboard-fore")
