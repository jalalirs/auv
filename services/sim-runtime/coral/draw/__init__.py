"""Drawing: the only code that writes the stage.

Systems compute; this draws what they computed, at the renderer's own rate,
from whatever the world holds. Nothing here changes the dive, so a dive flown
undrawn computes exactly what a drawn one does.

    propellers    each thruster's propeller, turned to where it is in its turn
    coral         a colony the vehicle broke, cut down to a stump
    sediment      the sand in the water, as flecks
    light         a tank's lamps and the window's daylight, by the dive's day
    tether        the cable, where its own solve says it is
"""
