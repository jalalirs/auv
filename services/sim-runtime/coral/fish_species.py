"""Who the fish are: one sheet per species, read by the fish's minds.

Each sheet is what a species does that a viewer — or a vehicle's camera — can
see: how big it is, how it swims, who it swims with, where it lives, when it
is up and where it sleeps, and how close it lets a vehicle come. Values are
the middle of published ranges (FishBase for sizes, diets and activity; the
behaviour literature for swimming and space use) and are *assumed* in this
platform's sense: chosen from a source, not measured here. A sheet that says
where a number came from is in `from`.

Swimming is burst-and-coast, which is how almost every small reef fish
actually moves (Calovi et al. 2018; Lei et al. 2020): a kick of a tenth of a
second or so that turns and accelerates the fish, then a straight glide that
decays. Speeds are in body lengths a second, so one sheet serves a juvenile
and an adult.

    kick_s        mean time between kicks while active (cruising)
    burst_bl      speed a kick gives, body lengths a second
    coast_s       how fast the glide decays (e-folding time)
    turn_deg      the largest heading change one kick makes
    school        None, or {"neighbours": k, "range_bl": r, "attract": a, "align": b}
    territory_m   radius it defends round its home (None: it roams)
    home_m        how far it ranges from home in a day (reef scale)
    altitude_m    (mean, sd) height above the bottom it holds while active
    activity      diurnal, nocturnal or crepuscular
    refuge        where it spends the time it is not active: branch, crevice,
                  burrow, host, or open (hovers in place)
    diet          plankton, algae, inverts or fish: what foraging looks like
    flight_m      flight initiation distance from an approaching vehicle
"""

from __future__ import annotations

SPECIES = {
    # ── a reef tank's fish ───────────────────────────────────────────────────
    "chromis_viridis": dict(
        common="blue-green chromis", group="damselfish", plan="deep", length=(0.055, 0.08),
        palette=((0.08, 0.42, 0.55), (0.62, 0.88, 0.85), (0.20, 0.70, 0.72)), mark="none",
        kick_s=0.45, burst_bl=4.0, coast_s=0.6, turn_deg=60,
        school=dict(neighbours=2, range_bl=10.0, attract=0.9, align=0.7),
        territory_m=None, home_m=3.0, altitude_m=(0.6, 0.3), activity="diurnal", refuge="branch",
        diet="plankton", flight_m=1.0,
        **{"from": "FishBase: Chromis viridis, to 10 cm TL, planktivore, aggregates over Acropora and shelters in it at night"}),
    "amphiprion_ocellaris": dict(
        common="ocellaris clownfish", group="damselfish", plan="fusiform", length=(0.06, 0.09),
        palette=((0.95, 0.40, 0.05), (0.98, 0.55, 0.15), (0.98, 0.98, 0.96)), mark="bands",
        kick_s=0.35, burst_bl=3.0, coast_s=0.35, turn_deg=75,
        school=None, territory_m=0.5, home_m=0.5, altitude_m=(0.15, 0.08), activity="diurnal",
        refuge="host", diet="plankton", flight_m=0.6,
        **{"from": "FishBase: Amphiprion ocellaris, to 11 cm, lives within a metre of its host anemone"}),
    "zebrasoma_flavescens": dict(
        common="yellow tang", group="surgeonfish", plan="deep", length=(0.12, 0.18),
        palette=((0.97, 0.82, 0.05), (0.99, 0.90, 0.25), (0.98, 0.98, 0.96)), mark="tail",
        kick_s=0.7, burst_bl=2.2, coast_s=0.9, turn_deg=45,
        school=dict(neighbours=1, range_bl=6.0, attract=0.3, align=0.4),
        territory_m=None, home_m=20.0, altitude_m=(0.25, 0.15), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=1.5,
        **{"from": "FishBase: Zebrasoma flavescens, to 20 cm, grazes turf algae over reef flats by day"}),
    "pseudocheilinus_hexataenia": dict(
        common="six-line wrasse", group="wrasse", plan="elongate", length=(0.05, 0.075),
        palette=((0.45, 0.20, 0.55), (0.85, 0.55, 0.30), (0.98, 0.60, 0.10)), mark="stripes",
        kick_s=0.28, burst_bl=5.0, coast_s=0.25, turn_deg=90,
        school=None, territory_m=0.4, home_m=1.0, altitude_m=(0.06, 0.04), activity="diurnal",
        refuge="crevice", diet="inverts", flight_m=0.4,
        **{"from": "FishBase: Pseudocheilinus hexataenia, to 10 cm, cryptic among coral branches, picks small invertebrates"}),
    "chelmon_rostratus": dict(
        common="copperband butterflyfish", group="butterflyfish", plan="deep", length=(0.11, 0.16),
        palette=((0.95, 0.94, 0.88), (0.98, 0.97, 0.94), (0.90, 0.45, 0.10)), mark="bars",
        kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.6, align=0.6),
        territory_m=None, home_m=15.0, altitude_m=(0.12, 0.08), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=1.2,
        **{"from": "FishBase: Chelmon rostratus, to 20 cm, in pairs, picks invertebrates from rock with its long snout"}),
    "amblyeleotris_wheeleri": dict(
        common="Wheeler's shrimp goby", group="bottom", plan="elongate", length=(0.06, 0.08),
        palette=((0.92, 0.85, 0.70), (0.97, 0.94, 0.85), (0.85, 0.30, 0.20)), mark="bars",
        kick_s=1.6, burst_bl=4.0, coast_s=0.2, turn_deg=80,
        school=None, territory_m=0.15, home_m=0.3, altitude_m=(0.02, 0.01), activity="diurnal",
        refuge="burrow", diet="plankton", flight_m=0.8,
        **{"from": "FishBase: Amblyeleotris wheeleri, to 8 cm, sits at the mouth of a burrow shared with a shrimp, dives into it when alarmed"}),
    "pterapogon_kauderni": dict(
        common="Banggai cardinalfish", group="solitary", plan="deep", length=(0.05, 0.08),
        palette=((0.70, 0.72, 0.70), (0.90, 0.90, 0.88), (0.04, 0.04, 0.05)), mark="bars",
        kick_s=1.2, burst_bl=2.0, coast_s=0.9, turn_deg=35,
        school=dict(neighbours=2, range_bl=6.0, attract=0.7, align=0.5),
        territory_m=None, home_m=1.0, altitude_m=(0.25, 0.1), activity="nocturnal", refuge="open",
        diet="plankton", flight_m=0.6,
        **{"from": "FishBase: Pterapogon kauderni, to 8 cm, hovers in small groups among sea urchins and anemones by day, feeds at night"}),

    # ── the reef's behaviour groups, each as a species that stands for it ────
    "scarus_iseri": dict(
        common="striped parrotfish", group="parrotfish", plan="fusiform", length=(0.2, 0.35),
        palette=((0.10, 0.45, 0.42), (0.55, 0.75, 0.68), (0.85, 0.45, 0.60)), mark="stripes",
        kick_s=0.8, burst_bl=2.0, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=2, range_bl=8.0, attract=0.4, align=0.4),
        territory_m=None, home_m=40.0, altitude_m=(0.6, 0.4), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=4.0,
        **{"from": "FishBase: Scarus iseri, to 35 cm, grazes in roving groups by day, sleeps in a mucus cocoon in a crevice"}),
    "ocyurus_chrysurus": dict(
        common="yellowtail snapper", group="snapper", plan="fusiform", length=(0.25, 0.4),
        palette=((0.45, 0.45, 0.55), (0.85, 0.85, 0.82), (0.98, 0.85, 0.15)), mark="stripes",
        kick_s=0.9, burst_bl=2.2, coast_s=1.2, turn_deg=35,
        school=dict(neighbours=3, range_bl=8.0, attract=0.8, align=0.8),
        territory_m=None, home_m=200.0, altitude_m=(2.5, 1.2), activity="crepuscular", refuge="open",
        diet="fish", flight_m=6.0,
        **{"from": "FishBase: Ocyurus chrysurus, to 86 cm, schools in mid-water, feeds mostly at night and dusk"}),
    "acanthurus_coeruleus": dict(
        common="blue tang", group="surgeonfish", plan="deep", length=(0.15, 0.3),
        palette=((0.10, 0.20, 0.55), (0.30, 0.45, 0.75), (0.95, 0.85, 0.15)), mark="tail",
        kick_s=0.8, burst_bl=2.0, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=3, range_bl=8.0, attract=0.6, align=0.6),
        territory_m=None, home_m=60.0, altitude_m=(1.0, 0.6), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=4.0,
        **{"from": "FishBase: Acanthurus coeruleus, to 39 cm, grazes in roving schools by day"}),
    "chromis_cyanea": dict(
        common="blue chromis", group="damselfish", plan="deep", length=(0.07, 0.12),
        palette=((0.05, 0.25, 0.60), (0.25, 0.50, 0.80), (0.05, 0.05, 0.10)), mark="tail",
        kick_s=0.45, burst_bl=4.0, coast_s=0.6, turn_deg=60,
        school=dict(neighbours=2, range_bl=10.0, attract=0.9, align=0.7),
        territory_m=None, home_m=8.0, altitude_m=(1.2, 0.8), activity="diurnal", refuge="branch",
        diet="plankton", flight_m=2.5,
        **{"from": "FishBase: Chromis cyanea, to 15 cm, feeds on plankton in aggregations above the reef"}),
    "thalassoma_bifasciatum": dict(
        common="bluehead wrasse", group="wrasse", plan="elongate", length=(0.08, 0.15),
        palette=((0.85, 0.80, 0.20), (0.95, 0.92, 0.70), (0.15, 0.40, 0.85)), mark="stripes",
        kick_s=0.3, burst_bl=4.5, coast_s=0.3, turn_deg=80,
        school=None, territory_m=None, home_m=15.0, altitude_m=(0.5, 0.3), activity="diurnal",
        refuge="burrow", diet="inverts", flight_m=2.0,
        **{"from": "FishBase: Thalassoma bifasciatum, to 25 cm, active forager by day, buries in sand at night"}),
    "chaetodon_capistratus": dict(
        common="foureye butterflyfish", group="butterflyfish", plan="deep", length=(0.07, 0.12),
        palette=((0.80, 0.80, 0.78), (0.95, 0.94, 0.90), (0.05, 0.05, 0.05)), mark="eyespot",
        kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=20.0, altitude_m=(0.8, 0.5), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=3.0,
        **{"from": "FishBase: Chaetodon capistratus, to 15 cm, in pairs, picks at coral polyps and worms"}),
    "caranx_ruber": dict(
        common="bar jack", group="jack", plan="fusiform", length=(0.3, 0.5),
        palette=((0.45, 0.55, 0.65), (0.85, 0.88, 0.90), (0.10, 0.20, 0.40)), mark="stripes",
        kick_s=1.0, burst_bl=2.5, coast_s=1.5, turn_deg=30,
        school=dict(neighbours=3, range_bl=6.0, attract=0.7, align=0.9),
        territory_m=None, home_m=1000.0, altitude_m=(4.0, 2.5), activity="diurnal", refuge="open",
        diet="fish", flight_m=6.0,
        **{"from": "FishBase: Caranx ruber, to 69 cm, fast-swimming predator in small schools over reefs"}),
    "epinephelus_guttatus": dict(
        common="red hind", group="solitary", plan="fusiform", length=(0.3, 0.5),
        palette=((0.70, 0.40, 0.30), (0.90, 0.75, 0.65), (0.75, 0.15, 0.10)), mark="spots",
        kick_s=2.0, burst_bl=1.5, coast_s=1.2, turn_deg=40,
        school=None, territory_m=5.0, home_m=30.0, altitude_m=(0.4, 0.3), activity="crepuscular",
        refuge="crevice", diet="fish", flight_m=3.0,
        **{"from": "FishBase: Epinephelus guttatus, to 76 cm, sit-and-wait predator holding a territory round a crevice"}),
    "coryphopterus_glaucofraenum": dict(
        common="bridled goby", group="bottom", plan="elongate", length=(0.04, 0.07),
        palette=((0.80, 0.78, 0.68), (0.95, 0.93, 0.85), (0.20, 0.18, 0.15)), mark="spots",
        kick_s=1.8, burst_bl=4.0, coast_s=0.2, turn_deg=80,
        school=None, territory_m=0.3, home_m=0.5, altitude_m=(0.02, 0.01), activity="diurnal",
        refuge="burrow", diet="inverts", flight_m=1.0,
        **{"from": "FishBase: Coryphopterus glaucofraenum, to 8 cm, rests on sand near rubble"}),
}

# Which species stands for each behaviour group, for a place whose record
# counts groups (a reef survey) rather than naming species (a stocked tank).
STANDS_FOR = {
    "parrotfish": "scarus_iseri", "snapper": "ocyurus_chrysurus", "surgeonfish": "acanthurus_coeruleus",
    "damselfish": "chromis_cyanea", "wrasse": "thalassoma_bifasciatum", "butterflyfish": "chaetodon_capistratus",
    "jack": "caranx_ruber", "solitary": "epinephelus_guttatus", "bottom": "coryphopterus_glaucofraenum",
}


# And for a tank whose record counts groups: the species a reef tank keeps.
STANDS_FOR_IN_A_TANK = {
    "damselfish": "chromis_viridis", "wrasse": "pseudocheilinus_hexataenia",
    "butterflyfish": "chelmon_rostratus", "bottom": "amblyeleotris_wheeleri",
    "surgeonfish": "zebrasoma_flavescens", "solitary": "pterapogon_kauderni",
}


def sheet(name: str) -> dict:
    """A species' sheet, by its own name or by the group it stands for."""
    if name in SPECIES:
        return SPECIES[name]
    if name in STANDS_FOR:
        return SPECIES[STANDS_FOR[name]]
    raise KeyError(f"no fish called {name!r}")


def species_of(name: str, tank: bool = False) -> str:
    """The species a name means: its own, or the one that stands for its
    group — a reef tank's, in a tank."""
    if name in SPECIES:
        return name
    if tank and name in STANDS_FOR_IN_A_TANK:
        return STANDS_FOR_IN_A_TANK[name]
    return STANDS_FOR[name]
