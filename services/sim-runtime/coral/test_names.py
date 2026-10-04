"""The old switch names still work, and the new ones win."""

import names


def test_an_old_name_is_given_its_new_one_and_a_new_one_is_kept():
    environ = {"CORAL_CITY_HOUR": "23", "CORAL_CITY_VEIL": "0.2", "IOCEAN_VEIL": "0.5", "PATH": "/bin"}
    given = names.carry(environ)
    assert environ["IOCEAN_HOUR"] == "23"
    assert environ["IOCEAN_VEIL"] == "0.5"
    assert given == ["IOCEAN_HOUR"]
