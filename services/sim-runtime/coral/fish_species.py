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

    # ── the Red Sea ──────────────────────────────────────────────────────────
    #
    # Two sources. The Jeddah airport tank (King Abdulaziz International,
    # Terminal 1: a ten-metre cylinder of Red Sea water fourteen metres tall),
    # filmed on 3 October 2026: the species named here from that footage say
    # `seen`, and `sure` is "seen" where the frames settle it and "probable"
    # where they do not. And the reef records of Al Fahal and Shushah
    # (iNaturalist, as tools/fauna fetched them): the species observed most in
    # each behaviour group, so that a Red Sea reef is drawn as the fish seen on
    # it. Sizes are FishBase's common length to its maximum; behaviour from the
    # same and the reef-fish literature, as for the rest. Colours are the
    # fish's own, which the water then takes its share of.
    "carcharhinus_melanopterus": dict(
        common="blacktip reef shark", group="shark", plan="shark", length=(1.0, 1.6),
        palette=((0.50, 0.48, 0.42), (0.92, 0.91, 0.88), (0.03, 0.03, 0.03)), marks=["tips"],
        kick_s=0.6, burst_bl=0.9, coast_s=3.0, turn_deg=25,
        school=None, territory_m=None, home_m=600.0, altitude_m=(1.5, 1.0), activity="crepuscular",
        refuge="open", diet="fish", flight_m=2.0, sure="seen", seen="jeddah 2: 0:36, 1:00 — several, black tips on dorsal and tail",
        **{"from": "FishBase: Carcharhinus melanopterus, to 200 cm, common 140; reef flats and lagoons, swims continuously, hunts small fish most at dusk and night"}),
    "plectorhinchus_gaterinus": dict(
        common="blackspotted rubberlip", group="snapper", plan="fusiform", length=(0.3, 0.45),
        form=dict(deep=0.34, tailshape="truncate", fin=0.12),
        palette=((0.72, 0.70, 0.52), (0.92, 0.90, 0.78), (0.03, 0.03, 0.03)), fins=(0.95, 0.85, 0.15),
        marks=["dots"], kick_s=1.0, burst_bl=1.6, coast_s=1.2, turn_deg=35,
        school=dict(neighbours=3, range_bl=4.0, attract=0.7, align=0.6),
        territory_m=None, home_m=80.0, altitude_m=(0.8, 0.5), activity="nocturnal", refuge="open",
        diet="inverts", flight_m=3.0, sure="seen", seen="jeddah 2: 0:36, 1:03 — several, yellow fins, black spots",
        **{"from": "FishBase: Plectorhinchus gaterinus, to 50 cm; hovers in groups under overhangs by day, feeds on bottom invertebrates at night"}),
    "acanthopagrus_bifasciatus": dict(
        common="twobar seabream", group="snapper", plan="deep", length=(0.3, 0.4),
        form=dict(deep=0.42, fin=0.14, tailshape="forked"),
        palette=((0.70, 0.72, 0.72), (0.94, 0.94, 0.92), (0.03, 0.03, 0.03)), fins=(0.95, 0.88, 0.20),
        marks=["headbars"], kick_s=0.8, burst_bl=2.0, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=2, range_bl=5.0, attract=0.5, align=0.5),
        territory_m=None, home_m=60.0, altitude_m=(1.0, 0.6), activity="diurnal", refuge="open",
        diet="inverts", flight_m=3.0, sure="seen", seen="jeddah 1: 0:33 — two black bars on the head, yellow fins and tail",
        **{"from": "FishBase: Acanthopagrus bifasciatus, to 50 cm; Red Sea and Gulf reefs, in small groups, takes invertebrates off the bottom"}),
    "rhabdosargus_haffara": dict(
        common="Haffara seabream", group="snapper", plan="deep", length=(0.18, 0.28),
        form=dict(deep=0.40, fin=0.12),
        palette=((0.72, 0.75, 0.76), (0.94, 0.94, 0.92), (0.95, 0.88, 0.20)), fins=(0.95, 0.88, 0.25),
        marks=[], kick_s=0.7, burst_bl=2.2, coast_s=0.9, turn_deg=45,
        school=dict(neighbours=4, range_bl=3.0, attract=0.9, align=0.8),
        territory_m=None, home_m=80.0, altitude_m=(2.0, 1.2), activity="diurnal", refuge="open",
        diet="inverts", flight_m=3.0, sure="probable",
        seen="jeddah 1: 0:33, 2: 0:45 — the big schools, silver with yellow tail and fins; species not settled from the footage",
        **{"from": "FishBase: Rhabdosargus haffara, to 35 cm; Red Sea endemic sparid of shallow reefs and seagrass, in schools"}),
    "pomacanthus_maculosus": dict(
        common="yellowbar angelfish", group="butterflyfish", plan="deep", length=(0.25, 0.4),
        form=dict(deep=0.58, fin=0.30, tailshape="truncate"),
        palette=((0.06, 0.12, 0.42), (0.12, 0.24, 0.58), (0.98, 0.86, 0.08)), fins=(0.10, 0.18, 0.50),
        marks=["bar"], kick_s=0.9, burst_bl=1.4, coast_s=1.1, turn_deg=40,
        school=None, territory_m=3.0, home_m=20.0, altitude_m=(0.6, 0.3), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.5, sure="seen", seen="jeddah 2: 0:09 — dark blue, a yellow bar across the middle",
        **{"from": "FishBase: Pomacanthus maculosus, to 50 cm; Red Sea and Gulf, territorial over reef, feeds on sponges and tunicates"}),
    "chaetodon_auriga": dict(
        common="threadfin butterflyfish", group="butterflyfish", plan="deep", length=(0.15, 0.2),
        form=dict(deep=0.56, fin=0.26, tailshape="truncate"),
        palette=((0.92, 0.92, 0.90), (0.98, 0.98, 0.96), (0.98, 0.82, 0.10)),
        marks=["chevrons", "rear", "eyebar"], kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=30.0, altitude_m=(0.5, 0.3), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.5, sure="seen", seen="jeddah 2: 0:09 — white with chevron lines, yellow rear, black eye bar",
        **{"from": "FishBase: Chaetodon auriga, to 23 cm; in pairs over reef and rubble, picks polyps, worms and algae"}),
    "abudefduf_vaigiensis": dict(
        common="Indo-Pacific sergeant", group="damselfish", plan="deep", length=(0.12, 0.18),
        form=dict(deep=0.48),
        palette=((0.78, 0.82, 0.55), (0.95, 0.96, 0.94), (0.03, 0.03, 0.04)),
        marks=["sergeant"], kick_s=0.45, burst_bl=3.5, coast_s=0.6, turn_deg=60,
        school=dict(neighbours=3, range_bl=6.0, attract=0.8, align=0.6),
        territory_m=None, home_m=20.0, altitude_m=(1.5, 1.0), activity="diurnal", refuge="crevice",
        diet="plankton", flight_m=1.5, sure="seen", seen="jeddah 1 and 2 throughout — five black bars, yellowish back",
        **{"from": "FishBase: Abudefduf vaigiensis, to 20 cm; in aggregations above the reef, feeds on plankton and algae"}),
    "platax_teira": dict(
        common="longfin batfish", group="solitary", plan="disc", length=(0.35, 0.5),
        palette=((0.72, 0.74, 0.72), (0.92, 0.92, 0.90), (0.06, 0.06, 0.07)), fins=(0.80, 0.78, 0.55),
        marks=["batfish"], kick_s=1.4, burst_bl=1.2, coast_s=1.6, turn_deg=30,
        school=dict(neighbours=3, range_bl=4.0, attract=0.6, align=0.7),
        territory_m=None, home_m=200.0, altitude_m=(3.0, 1.5), activity="diurnal", refuge="open",
        diet="plankton", flight_m=2.0, sure="probable", seen="jeddah 1 and 2 — many large batfish; teira over orbicularis by the dark bars, not settled",
        **{"from": "FishBase: Platax teira, to 70 cm; in schools in open water over reefs, omnivore"}),
    "epinephelus_lanceolatus": dict(
        common="giant grouper", group="solitary", plan="grouper", length=(1.0, 1.6),
        palette=((0.62, 0.62, 0.55), (0.82, 0.80, 0.72), (0.06, 0.06, 0.06)),
        marks=["blotches"], kick_s=2.5, burst_bl=1.2, coast_s=1.5, turn_deg=35,
        school=None, territory_m=8.0, home_m=60.0, altitude_m=(0.3, 0.2), activity="crepuscular", refuge="crevice",
        diet="fish", flight_m=2.0, sure="probable",
        seen="jeddah 2: 0:00 — a big grouper on the sand, dark blotches on pale; could be brown-marbled",
        **{"from": "FishBase: Epinephelus lanceolatus, to 270 cm; the largest reef bony fish, sits by caves and wrecks, eats fish, rays and crustaceans"}),
    "naso_hexacanthus": dict(
        common="sleek unicornfish", group="surgeonfish", plan="fusiform", length=(0.4, 0.6),
        form=dict(deep=0.34, nose=0.06, hump=0.12, tailshape="lunate"),
        palette=((0.60, 0.64, 0.68), (0.86, 0.88, 0.90), (0.40, 0.45, 0.50)),
        marks=[], kick_s=0.9, burst_bl=1.8, coast_s=1.4, turn_deg=35,
        school=dict(neighbours=3, range_bl=5.0, attract=0.6, align=0.8),
        territory_m=None, home_m=300.0, altitude_m=(4.0, 2.0), activity="diurnal", refuge="open",
        diet="plankton", flight_m=4.0, sure="probable", seen="jeddah 2: 0:45 — pale, blunt-headed; species not settled",
        **{"from": "FishBase: Naso hexacanthus, to 75 cm; in schools in mid-water off reef slopes, feeds on zooplankton"}),
    "aetobatus_ocellatus": dict(
        common="ocellated eagle ray", group="ray", plan="ray", length=(1.6, 2.4),
        palette=((0.70, 0.70, 0.68), (0.95, 0.95, 0.93), (0.95, 0.95, 0.93)),
        marks=[], kick_s=2.0, burst_bl=0.5, coast_s=3.0, turn_deg=25,
        school=None, territory_m=None, home_m=800.0, altitude_m=(1.5, 1.0), activity="diurnal", refuge="open",
        diet="inverts", flight_m=3.0, sure="probable", seen="jeddah 2: 1:09, 1:12 — a large pale ray, pointed head, whip tail; species not settled",
        **{"from": "FishBase: Aetobatus ocellatus, disc to 300 cm; flies over reef and sand, digs out molluscs. Length here is nose to tail"}),
    # The reef's, by what Al Fahal's and Shushah's records saw most.
    "pseudanthias_squamipinnis": dict(
        common="lyretail anthias", group="damselfish", plan="deep", length=(0.07, 0.12),
        form=dict(deep=0.40, tailshape="lunate"),
        palette=((0.98, 0.50, 0.20), (0.99, 0.70, 0.45), (0.90, 0.30, 0.60)), marks=[],
        kick_s=0.35, burst_bl=4.5, coast_s=0.4, turn_deg=70,
        school=dict(neighbours=4, range_bl=5.0, attract=0.9, align=0.5),
        territory_m=None, home_m=3.0, altitude_m=(1.0, 0.6), activity="diurnal", refuge="crevice",
        diet="plankton", flight_m=1.2,
        **{"from": "FishBase: Pseudanthias squamipinnis, to 15 cm; in swarms of hundreds over coral heads, dives into the reef when threatened"}),
    "pomacentrus_sulfureus": dict(
        common="sulfur damsel", group="damselfish", plan="deep", length=(0.07, 0.1),
        palette=((0.98, 0.85, 0.10), (0.99, 0.92, 0.40), (0.05, 0.05, 0.05)), marks=[],
        kick_s=0.4, burst_bl=4.0, coast_s=0.5, turn_deg=70,
        school=None, territory_m=0.6, home_m=1.5, altitude_m=(0.3, 0.2), activity="diurnal", refuge="branch",
        diet="plankton", flight_m=1.0,
        **{"from": "FishBase: Pomacentrus sulfureus, to 11 cm; Red Sea, solitary over coral, feeds on plankton"}),
    "amphiprion_bicinctus": dict(
        common="Red Sea anemonefish", group="damselfish", plan="deep", length=(0.08, 0.12),
        form=dict(deep=0.44),
        palette=((0.90, 0.45, 0.05), (0.98, 0.70, 0.20), (0.98, 0.98, 0.96)), mark="bands",
        kick_s=0.35, burst_bl=3.0, coast_s=0.35, turn_deg=75,
        school=None, territory_m=0.5, home_m=0.5, altitude_m=(0.15, 0.08), activity="diurnal", refuge="host",
        diet="plankton", flight_m=0.6,
        **{"from": "FishBase: Amphiprion bicinctus, to 14 cm; Red Sea, lives in its host anemone"}),
    "pycnochromis_dimidiatus": dict(
        common="Red Sea half-and-half chromis", group="damselfish", plan="deep", length=(0.05, 0.08),
        palette=((0.92, 0.92, 0.90), (0.98, 0.98, 0.96), (0.04, 0.04, 0.05)), marks=["half"],
        kick_s=0.4, burst_bl=4.0, coast_s=0.5, turn_deg=65,
        school=dict(neighbours=3, range_bl=8.0, attract=0.8, align=0.6),
        territory_m=None, home_m=3.0, altitude_m=(0.8, 0.5), activity="diurnal", refuge="branch",
        diet="plankton", flight_m=1.0,
        **{"from": "FishBase: Pycnochromis dimidiatus, to 9 cm; Red Sea, aggregations over coral, front half black, back white"}),
    "amblyglyphidodon_indicus": dict(
        common="green damselfish", group="damselfish", plan="deep", length=(0.08, 0.12),
        form=dict(deep=0.55),
        palette=((0.70, 0.78, 0.55), (0.90, 0.92, 0.82), (0.95, 0.85, 0.20)), marks=["belly"],
        kick_s=0.45, burst_bl=3.5, coast_s=0.6, turn_deg=60,
        school=dict(neighbours=2, range_bl=8.0, attract=0.6, align=0.5),
        territory_m=None, home_m=4.0, altitude_m=(0.8, 0.5), activity="diurnal", refuge="branch",
        diet="plankton", flight_m=1.2,
        **{"from": "FishBase: Amblyglyphidodon indicus, to 13 cm; over branching coral on slopes"}),
    "thalassoma_rueppellii": dict(
        common="Klunzinger's wrasse", group="wrasse", plan="elongate", length=(0.12, 0.2),
        palette=((0.15, 0.55, 0.45), (0.45, 0.75, 0.70), (0.85, 0.30, 0.55)), marks=["checker"],
        kick_s=0.3, burst_bl=4.5, coast_s=0.3, turn_deg=80,
        school=None, territory_m=None, home_m=20.0, altitude_m=(0.5, 0.3), activity="diurnal", refuge="burrow",
        diet="inverts", flight_m=2.0,
        **{"from": "FishBase: Thalassoma rueppellii, to 20 cm; Red Sea endemic, quick forager over the reef top"}),
    "halichoeres_hortulanus": dict(
        common="checkerboard wrasse", group="wrasse", plan="elongate", length=(0.15, 0.25),
        form=dict(deep=0.20),
        palette=((0.20, 0.45, 0.40), (0.90, 0.90, 0.85), (0.05, 0.05, 0.06)), marks=["checker"],
        kick_s=0.35, burst_bl=4.0, coast_s=0.35, turn_deg=75,
        school=None, territory_m=None, home_m=30.0, altitude_m=(0.3, 0.2), activity="diurnal", refuge="burrow",
        diet="inverts", flight_m=2.0,
        **{"from": "FishBase: Halichoeres hortulanus, to 27 cm; over sand and rubble by reefs, buries at night"}),
    "cheilinus_undulatus": dict(
        common="Napoleon wrasse", group="wrasse", plan="fusiform", length=(0.8, 1.4),
        form=dict(deep=0.36, hump=0.25, tailshape="rounded", fin=0.10),
        palette=((0.25, 0.48, 0.45), (0.55, 0.72, 0.62), (0.15, 0.30, 0.30)), marks=["checker"],
        kick_s=1.4, burst_bl=1.2, coast_s=1.8, turn_deg=30,
        school=None, territory_m=None, home_m=400.0, altitude_m=(1.0, 0.6), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=4.0,
        **{"from": "FishBase: Cheilinus undulatus, to 229 cm; large wrasse with a hump on the forehead, eats molluscs and urchins"}),
    "scarus_ferrugineus": dict(
        common="rusty parrotfish", group="parrotfish", plan="fusiform", length=(0.25, 0.4),
        palette=((0.25, 0.55, 0.45), (0.55, 0.75, 0.62), (0.85, 0.75, 0.25)), mark="tail",
        kick_s=0.8, burst_bl=2.0, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=2, range_bl=8.0, attract=0.4, align=0.4),
        territory_m=None, home_m=60.0, altitude_m=(0.6, 0.4), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=4.0,
        **{"from": "FishBase: Scarus ferrugineus, to 41 cm; Red Sea and Gulf, grazes the reef in harems by day"}),
    "hipposcarus_harid": dict(
        common="Indian longnose parrotfish", group="parrotfish", plan="fusiform", length=(0.35, 0.55),
        form=dict(nose=0.14),
        palette=((0.40, 0.60, 0.65), (0.70, 0.80, 0.82), (0.60, 0.40, 0.55)), mark="tail",
        kick_s=0.8, burst_bl=2.0, coast_s=1.1, turn_deg=40,
        school=dict(neighbours=3, range_bl=8.0, attract=0.5, align=0.5),
        territory_m=None, home_m=100.0, altitude_m=(0.8, 0.5), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=4.5,
        **{"from": "FishBase: Hipposcarus harid, to 75 cm; grazes sandy reef margins in groups"}),
    "chlorurus_sordidus": dict(
        common="bullethead parrotfish", group="parrotfish", plan="fusiform", length=(0.2, 0.35),
        palette=((0.30, 0.30, 0.28), (0.55, 0.50, 0.45), (0.85, 0.70, 0.60)), mark="tail",
        kick_s=0.8, burst_bl=2.0, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=3, range_bl=8.0, attract=0.5, align=0.5),
        territory_m=None, home_m=50.0, altitude_m=(0.5, 0.3), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=4.0,
        **{"from": "FishBase: Chlorurus sordidus, to 40 cm; the commonest Indo-Pacific parrotfish, scrapes dead coral in groups"}),
    "heniochus_intermedius": dict(
        common="Red Sea bannerfish", group="butterflyfish", plan="deep", length=(0.14, 0.2),
        form=dict(deep=0.55, fin=0.22, dorsal="banner"),
        palette=((0.95, 0.94, 0.88), (0.98, 0.97, 0.94), (0.03, 0.03, 0.03)), fins=(0.98, 0.85, 0.15),
        marks=["banner"], kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=2, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=30.0, altitude_m=(1.0, 0.5), activity="diurnal", refuge="crevice",
        diet="plankton", flight_m=2.5,
        **{"from": "FishBase: Heniochus intermedius, to 20 cm; Red Sea, in pairs or groups, a long white dorsal filament"}),
    "chaetodon_semilarvatus": dict(
        common="masked butterflyfish", group="butterflyfish", plan="deep", length=(0.15, 0.22),
        form=dict(deep=0.58, tailshape="truncate"),
        palette=((0.98, 0.80, 0.12), (0.99, 0.88, 0.30), (0.25, 0.35, 0.55)),
        marks=["mask"], kick_s=1.0, burst_bl=1.4, coast_s=1.1, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=20.0, altitude_m=(0.8, 0.4), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.5,
        **{"from": "FishBase: Chaetodon semilarvatus, to 23 cm; Red Sea, in pairs, hangs still under table corals"}),
    "chaetodon_austriacus": dict(
        common="exquisite butterflyfish", group="butterflyfish", plan="deep", length=(0.1, 0.14),
        form=dict(deep=0.58, tailshape="truncate"),
        palette=((0.98, 0.70, 0.15), (0.99, 0.82, 0.35), (0.05, 0.05, 0.06)),
        marks=["eyebar", "tail"], kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=2.0, home_m=10.0, altitude_m=(0.4, 0.2), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.0,
        **{"from": "FishBase: Chaetodon austriacus, to 14 cm; Red Sea, pairs feeding on coral polyps"}),
    "chaetodon_fasciatus": dict(
        common="Red Sea raccoon butterflyfish", group="butterflyfish", plan="deep", length=(0.15, 0.22),
        form=dict(deep=0.56, tailshape="truncate"),
        palette=((0.98, 0.82, 0.15), (0.99, 0.90, 0.40), (0.05, 0.05, 0.06)),
        marks=["eyebar", "chevrons"], kick_s=0.9, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=dict(neighbours=1, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=20.0, altitude_m=(0.5, 0.3), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.5,
        **{"from": "FishBase: Chaetodon fasciatus, to 22 cm; Red Sea, in pairs or small groups"}),
    "pygoplites_diacanthus": dict(
        common="regal angelfish", group="butterflyfish", plan="deep", length=(0.15, 0.25),
        form=dict(deep=0.52, tailshape="truncate"),
        palette=((0.95, 0.65, 0.15), (0.98, 0.80, 0.35), (0.20, 0.25, 0.55)),
        marks=["sergeant"], kick_s=0.9, burst_bl=1.5, coast_s=1.0, turn_deg=40,
        school=None, territory_m=3.0, home_m=15.0, altitude_m=(0.4, 0.2), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=2.0,
        **{"from": "FishBase: Pygoplites diacanthus, to 25 cm; close to caves and overhangs, feeds on sponges"}),
    "acanthurus_sohal": dict(
        common="sohal surgeonfish", group="surgeonfish", plan="deep", length=(0.25, 0.4),
        form=dict(deep=0.46, tailshape="lunate"),
        palette=((0.35, 0.40, 0.45), (0.80, 0.82, 0.85), (0.98, 0.55, 0.10)), marks=["stripes"],
        kick_s=0.7, burst_bl=2.2, coast_s=0.9, turn_deg=45,
        school=None, territory_m=4.0, home_m=15.0, altitude_m=(0.3, 0.2), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=2.5,
        **{"from": "FishBase: Acanthurus sohal, to 40 cm; Red Sea, defends an algal patch on the reef crest fiercely"}),
    "ctenochaetus_striatus": dict(
        common="lined bristletooth", group="surgeonfish", plan="deep", length=(0.15, 0.25),
        form=dict(deep=0.44, tailshape="lunate"),
        palette=((0.30, 0.25, 0.20), (0.45, 0.38, 0.30), (0.55, 0.50, 0.30)), mark="none",
        kick_s=0.7, burst_bl=2.0, coast_s=0.9, turn_deg=45,
        school=dict(neighbours=3, range_bl=8.0, attract=0.6, align=0.6),
        territory_m=None, home_m=40.0, altitude_m=(0.3, 0.2), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=3.0,
        **{"from": "FishBase: Ctenochaetus striatus, to 26 cm; brushes detritus off the reef, often in mixed groups"}),
    "naso_elegans": dict(
        common="elegant unicornfish", group="surgeonfish", plan="fusiform", length=(0.3, 0.45),
        form=dict(deep=0.38, hump=0.08, tailshape="lunate"),
        palette=((0.28, 0.30, 0.32), (0.55, 0.55, 0.55), (0.98, 0.65, 0.10)), mark="tail",
        kick_s=0.8, burst_bl=2.0, coast_s=1.2, turn_deg=40,
        school=dict(neighbours=2, range_bl=8.0, attract=0.5, align=0.6),
        territory_m=None, home_m=100.0, altitude_m=(1.0, 0.6), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=3.5,
        **{"from": "FishBase: Naso elegans, to 45 cm; orange spines at the tail, grazes brown algae in groups"}),
    "zebrasoma_desjardinii": dict(
        common="Indian sailfin tang", group="surgeonfish", plan="deep", length=(0.2, 0.35),
        form=dict(deep=0.52, fin=0.36, dorsal="tall", anal=1.0),
        palette=((0.35, 0.32, 0.25), (0.75, 0.70, 0.55), (0.95, 0.85, 0.30)), mark="bars",
        kick_s=0.8, burst_bl=1.8, coast_s=1.0, turn_deg=45,
        school=dict(neighbours=1, range_bl=6.0, attract=0.4, align=0.4),
        territory_m=None, home_m=30.0, altitude_m=(0.4, 0.3), activity="diurnal", refuge="crevice",
        diet="algae", flight_m=2.5,
        **{"from": "FishBase: Zebrasoma desjardinii, to 40 cm; in pairs over reef flats, dorsal and anal fins like sails"}),
    "lutjanus_kasmira": dict(
        common="bluestriped snapper", group="snapper", plan="fusiform", length=(0.2, 0.35),
        palette=((0.95, 0.80, 0.20), (0.98, 0.88, 0.50), (0.35, 0.60, 0.95)), mark="stripes",
        kick_s=0.9, burst_bl=2.0, coast_s=1.1, turn_deg=40,
        school=dict(neighbours=4, range_bl=4.0, attract=0.9, align=0.8),
        territory_m=None, home_m=100.0, altitude_m=(1.0, 0.6), activity="nocturnal", refuge="open",
        diet="fish", flight_m=3.0,
        **{"from": "FishBase: Lutjanus kasmira, to 40 cm; hangs in dense schools by coral heads by day, hunts at night"}),
    "macolor_niger": dict(
        common="black-and-white snapper", group="snapper", plan="fusiform", length=(0.35, 0.55),
        form=dict(deep=0.36),
        palette=((0.12, 0.12, 0.14), (0.30, 0.30, 0.32), (0.85, 0.85, 0.85)), marks=["belly"],
        kick_s=1.0, burst_bl=1.8, coast_s=1.3, turn_deg=35,
        school=dict(neighbours=3, range_bl=5.0, attract=0.7, align=0.7),
        territory_m=None, home_m=200.0, altitude_m=(2.0, 1.0), activity="nocturnal", refuge="open",
        diet="plankton", flight_m=4.0,
        **{"from": "FishBase: Macolor niger, to 75 cm; schools on steep reef slopes, feeds on zooplankton at night"}),
    "monotaxis_grandoculis": dict(
        common="humpnose big-eye bream", group="snapper", plan="deep", length=(0.3, 0.45),
        form=dict(deep=0.42, hump=0.10),
        palette=((0.55, 0.55, 0.55), (0.85, 0.85, 0.82), (0.95, 0.80, 0.30)), mark="none",
        kick_s=1.0, burst_bl=1.8, coast_s=1.2, turn_deg=35,
        school=dict(neighbours=3, range_bl=5.0, attract=0.6, align=0.6),
        territory_m=None, home_m=150.0, altitude_m=(1.0, 0.6), activity="nocturnal", refuge="open",
        diet="inverts", flight_m=3.5,
        **{"from": "FishBase: Monotaxis grandoculis, to 60 cm; groups over sand near reefs by day, feeds at night"}),
    "lethrinus_mahsena": dict(
        common="mahsena emperor", group="snapper", plan="fusiform", length=(0.3, 0.5),
        form=dict(deep=0.36),
        palette=((0.55, 0.55, 0.45), (0.80, 0.78, 0.68), (0.70, 0.30, 0.20)), mark="bars",
        kick_s=1.0, burst_bl=1.8, coast_s=1.2, turn_deg=35,
        school=dict(neighbours=2, range_bl=6.0, attract=0.4, align=0.4),
        territory_m=None, home_m=200.0, altitude_m=(0.8, 0.5), activity="diurnal", refuge="open",
        diet="inverts", flight_m=4.0,
        **{"from": "FishBase: Lethrinus mahsena, to 65 cm; forages over sand and seagrass beside reefs"}),
    "plectropomus_marisrubri": dict(
        common="Red Sea leopard grouper", group="solitary", plan="grouper", length=(0.4, 0.65),
        palette=((0.75, 0.30, 0.22), (0.88, 0.50, 0.40), (0.35, 0.60, 0.95)), marks=[("dots", (0.35, 0.60, 0.95))],
        kick_s=2.0, burst_bl=1.6, coast_s=1.2, turn_deg=40,
        school=None, territory_m=6.0, home_m=60.0, altitude_m=(0.4, 0.3), activity="crepuscular", refuge="crevice",
        diet="fish", flight_m=3.0,
        **{"from": "FishBase: Plectropomus marisrubri, to 80 cm; Red Sea, red with blue spots, ambushes fish"}),
    "cephalopholis_miniata": dict(
        common="coral grouper", group="solitary", plan="grouper", length=(0.25, 0.4),
        palette=((0.80, 0.20, 0.15), (0.92, 0.35, 0.25), (0.40, 0.65, 0.95)), marks=[("dots", (0.40, 0.65, 0.95))],
        kick_s=2.0, burst_bl=1.6, coast_s=1.0, turn_deg=40,
        school=None, territory_m=4.0, home_m=20.0, altitude_m=(0.3, 0.2), activity="crepuscular", refuge="crevice",
        diet="fish", flight_m=2.5,
        **{"from": "FishBase: Cephalopholis miniata, to 45 cm; red with blue spots, holds a territory on the reef face"}),
    "paracirrhites_forsteri": dict(
        common="freckled hawkfish", group="bottom", plan="fusiform", length=(0.15, 0.22),
        palette=((0.60, 0.35, 0.30), (0.90, 0.85, 0.80), (0.05, 0.05, 0.05)), marks=["dots"],
        kick_s=2.5, burst_bl=3.0, coast_s=0.3, turn_deg=70,
        school=None, territory_m=0.8, home_m=1.5, altitude_m=(0.05, 0.03), activity="diurnal", refuge="branch",
        diet="fish", flight_m=1.0,
        **{"from": "FishBase: Paracirrhites forsteri, to 22 cm; perches on coral heads and darts at small fish"}),
    "arothron_diadematus": dict(
        common="masked puffer", group="solitary", plan="fusiform", length=(0.2, 0.3),
        form=dict(deep=0.36, wide=0.30, tailshape="rounded", fin=0.07),
        palette=((0.70, 0.68, 0.62), (0.90, 0.88, 0.82), (0.05, 0.05, 0.06)), marks=["eyebar"],
        kick_s=1.8, burst_bl=1.0, coast_s=0.8, turn_deg=50,
        school=None, territory_m=None, home_m=20.0, altitude_m=(0.5, 0.3), activity="diurnal", refuge="crevice",
        diet="inverts", flight_m=1.5,
        **{"from": "FishBase: Arothron diadematus, to 30 cm; Red Sea, a dark mask over the eyes, slow and solitary"}),
    "flavocaranx_bajad": dict(
        common="orange-spotted trevally", group="jack", plan="fusiform", length=(0.3, 0.5),
        form=dict(tailshape="lunate"),
        palette=((0.55, 0.58, 0.60), (0.85, 0.88, 0.90), (0.98, 0.75, 0.15)), marks=["dots"],
        kick_s=1.0, burst_bl=2.5, coast_s=1.5, turn_deg=30,
        school=dict(neighbours=3, range_bl=6.0, attract=0.7, align=0.9),
        territory_m=None, home_m=800.0, altitude_m=(2.0, 1.5), activity="diurnal", refuge="open",
        diet="fish", flight_m=5.0,
        **{"from": "FishBase: Carangoides bajad, to 55 cm; hunts along the reef edge, sometimes gold all over"}),
    "amblyeleotris_steinitzi": dict(
        common="Steinitz's shrimpgoby", group="bottom", plan="elongate", length=(0.06, 0.08),
        palette=((0.88, 0.82, 0.70), (0.96, 0.93, 0.85), (0.55, 0.30, 0.20)), mark="bars",
        kick_s=1.6, burst_bl=4.0, coast_s=0.2, turn_deg=80,
        school=None, territory_m=0.15, home_m=0.3, altitude_m=(0.02, 0.01), activity="diurnal",
        refuge="burrow", diet="plankton", flight_m=0.8,
        **{"from": "FishBase: Amblyeleotris steinitzi, to 8 cm; at the mouth of a burrow it shares with a shrimp"}),
    "parapercis_hexophtalma": dict(
        common="speckled sandperch", group="bottom", plan="elongate", length=(0.15, 0.25),
        palette=((0.85, 0.80, 0.70), (0.95, 0.92, 0.85), (0.05, 0.05, 0.06)), marks=["dots"],
        kick_s=2.0, burst_bl=3.5, coast_s=0.3, turn_deg=70,
        school=None, territory_m=1.0, home_m=3.0, altitude_m=(0.02, 0.01), activity="diurnal",
        refuge="burrow", diet="inverts", flight_m=1.5,
        **{"from": "FishBase: Parapercis hexophtalma, to 29 cm; rests on sand propped on its pelvic fins"}),
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


def key_of(taxon: str) -> str:
    """A record's species name as a sheet's key: 'Plectorhinchus gaterinus'
    is plectorhinchus_gaterinus."""
    return "_".join(taxon.lower().split()[:2])


def recorded(counted, group_of, most: int = 3) -> dict:
    """For each behaviour group, the species seen at a place that have a
    sheet, most-observed first, with their share of the group: so a group is
    drawn as the fish actually recorded there, and a Red Sea reef as Red Sea
    fish. A group with none of its own sheets falls back to its stand-in."""
    seen: dict[str, dict[str, int]] = {}
    for one in counted or []:
        if one.get("group") != "Actinopterygii":
            continue
        key = key_of(one.get("taxon", ""))
        if key not in SPECIES:
            continue
        group = group_of(one["taxon"])
        seen.setdefault(group, {})
        seen[group][key] = seen[group].get(key, 0) + int(one.get("observations", 0))
    out = {}
    for group, species in seen.items():
        top = sorted(species.items(), key=lambda kv: -kv[1])[:most]
        total = sum(n for _, n in top) or 1
        out[group] = [(k, n / total) for k, n in top]
    return out


def split(groups: dict, by: dict) -> dict:
    """A count per group as a count per species, by `recorded`'s shares."""
    out: dict[str, int] = {}
    for group, many in groups.items():
        parts = by.get(group)
        if not parts:
            out[group] = out.get(group, 0) + int(many)
            continue
        left = int(many)
        for i, (species, share) in enumerate(parts):
            take = left if i == len(parts) - 1 else int(round(many * share))
            take = max(0, min(left, take))
            out[species] = out.get(species, 0) + take
            left -= take
    return {k: v for k, v in out.items() if v}


def species_of(name: str, tank: bool = False) -> str:
    """The species a name means: its own, or the one that stands for its
    group — a reef tank's, in a tank."""
    if name in SPECIES:
        return name
    if tank and name in STANDS_FOR_IN_A_TANK:
        return STANDS_FOR_IN_A_TANK[name]
    return STANDS_FOR[name]
