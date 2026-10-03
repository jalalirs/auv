"""What a vehicle did to the place it flew in, as rows a report can print.

A survey's sponsor asks two things a flight log does not answer: what did the
vehicle do to the reef, and how much did its being there change what it
counted. The second needs the same dive flown again with fish that cannot see
the vehicle (tools/count-bias). The first is here: the fish it put to flight
and ran into, the coral it struck, broke, tore off and smothered, the polyps
it shut, the sand it lifted and what that cost the water.

Every row says what it is. None is a measurement of a real reef: each is what
a model with stated physics computed, so each is *derived*, and its `from`
names the model and what in it was assumed. A disturbance figure printed
without that is the figure that gets quoted back as an observation.
"""

from __future__ import annotations

DERIVED = "derived"

FISH_FLED = ("derived: Hein et al. 2018's looming rule — a fish bolts when the vehicle grows in its view "
             "faster than a threshold set by its species' flight initiation distance (fish_species.py); "
             "the threshold's steepness is assumed")
FISH_STRUCK = "derived: the hull's swept box against each fish's body, counted once per contact"
GROUND = "derived: the hull against the place's seabed, counted once per contact"
POLYPS = ("derived: polyps withdraw when the wash passes 8 cm/s or the hull touches, and reopen over a "
          "quarter-hour of the day; both figures assumed from aquarium accounts")
SMOTHER = ("derived: settled sediment against 10 mg/cm² a day, where harm to coral begins, and 50, where "
           "it is severe (Erftemeijer et al. 2012)")


def rows(life: dict | None, coral: dict | None, sediment: dict | None, hit: dict | None) -> list[dict]:
    """The disturbance of one dive, from what its systems said at the end."""
    out: list[dict] = []

    def row(what: str, value, unit: str, from_: str) -> None:
        out.append({"what": what, "value": value, "unit": unit, "kind": DERIVED, "from": from_})

    if life and life.get("fish"):
        row("fish put to flight by the vehicle", int(life.get("fledTheVehicle", 0)),
            f"of {int(life['fish'])}", FISH_FLED)
        row("fish the vehicle ran into", int(life.get("bumped", 0)), "fish", FISH_STRUCK)
    if coral and coral.get("colonies"):
        how = coral.get("from") or "the coral system"
        row("colonies struck", int(coral.get("struck", 0)), f"of {int(coral['colonies'])}",
            f"derived: the hull against each colony's solid; {how}")
        row("colonies brushed", int(coral.get("brushed", 0)), "colonies",
            f"derived: the hull inside a colony's reach without striking its skeleton; {how}")
        row("colonies broken", len(coral.get("broken", [])), "colonies",
            f"derived: bending stress against the skeleton's strength; {how}")
        row("colonies torn off their rock", len(coral.get("tornOff", [])), "colonies",
            "derived: the force on a massive colony against its attachment, assumed a tenth of the "
            "skeleton's strength (Madin et al. 2014 for the substrate)")
        if "smothered" in coral:
            row("colonies smothered", int(coral["smothered"]), "colonies", SMOTHER)
            row("of them badly", int(coral.get("smotheredBadly", 0)), "colonies", SMOTHER)
        if "disturbed" in coral:
            row("colonies that shut their polyps", int(coral["disturbed"]), "colonies", POLYPS)
    if sediment:
        how = sediment.get("from") or "the sediment system"
        row("sand lifted", float(sediment.get("liftedG", 0.0)), "g", how)
        row("sand settled again", float(sediment.get("settledG", 0.0)), "g", how)
        if sediment.get("worstOnACoralMgCm2") is not None:
            row("most settled on one colony", float(sediment["worstOnACoralMgCm2"]), "mg/cm²", how)
        if sediment.get("worstVisibilityM") is not None:
            row("worst visibility in front of the camera", float(sediment["worstVisibilityM"]), "m",
                how + "; visibility from the suspended mass by Davies-Colley's beam attenuation")
    if hit is not None:
        row("times it touched the ground", int(hit.get("ground", 0)), "contacts", GROUND)
    return out


def counted_share(seeing: int, blind: int) -> dict | None:
    """The share of the fish that were there that the vehicle counted: the
    dive against its twin whose fish could not see it, on the same seed."""
    if not blind:
        return None
    return {"what": "share of the fish there that the camera counted", "value": round(seeing / blind, 3),
            "unit": f"{seeing} of {blind}", "kind": DERIVED,
            "from": ("derived: the same dive flown twice on one seed, once with fish that see the vehicle and "
                     "once with fish blind to it; each fish counted once when the camera first sees it")}
