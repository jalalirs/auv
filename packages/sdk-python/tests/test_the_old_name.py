"""A controller written against `coral_city` gets iocean's own objects."""

import importlib


def test_the_old_name_is_the_same_sdk_and_not_a_copy():
    import coral_city
    import iocean

    assert coral_city.Controller is iocean.Controller
    assert coral_city.Observation is iocean.Observation


def test_its_modules_are_iocean_s_modules():
    old = importlib.import_module("coral_city.interface")
    new = importlib.import_module("iocean.interface")
    assert old is new
    from coral_city.interface import Command
    from iocean.interface import Command as Same
    assert Command is Same
    from coral_city.vehicles import __name__ as said
    assert said == "iocean.vehicles"
