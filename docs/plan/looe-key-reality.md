# Looe Key, as measured

What the reef the platform is built against actually is, from the people who
measured it, and what that does to the model. Written on 2 September 2026,
when the procedurally grown reef was thrown out.

## The verdict on the grown reef

The reef in `tools/reef.py` and `tools/zonation.py` put 86% coral cover on
Looe Key, drawn from a depth curve peaked at eight metres, and started the
dive at (210, −230) because that cell scored 94% cover. The Florida Fish and
Wildlife Conservation Commission has photographed fixed stations on this reef
every year since 1996. Their 2024 numbers:

| station | depth | stony coral | octocoral | sponge | zoanthid | macroalgae | bare substrate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Looe Key Shallow | 7 m | 3.4% | 5.1% | 2.1% | 4.3% | 21.8% | 62.3% |
| Looe Key Deep | 12.5 m | 4.4% | 9.8% | 7.7% | 0.1% | 16.8% | 60.6% |

In 1996 the shallow station had 19% stony coral. It has lost five sixths of it.

The habitat map puts (210, −230) on unconsolidated sediment. The dive was
starting on sand.

So: the model was wrong by an order of magnitude in cover, wrong in what the
cover was made of, and wrong about where the reef is. Nothing in it can be
tuned into being right, because none of it was anchored to a measurement.

## The sources

Everything below is public, licensed for this use, and fetched by a tool in
this repository so it can be fetched again.

**Bathymetry.** NOAA NCEI DEM mosaic, 2 m samples over the 1 km square, from
the Key West lidar surveys. Already in the site. It is smooth: real spurs have
metre-scale relief the 2 m grid rounds off.

**The reef itself, at 5 mm.** The U.S. Geological Survey flew a five-camera
photogrammetry sled over the fore reef in July 2022 (DOI 10.5066/P1QRS3SK):
an 850 × 160 m orthomosaic at 5 mm, a 1 cm digital elevation model, and a
10.5 billion point cloud, all public domain. The strip covers the
spur-and-groove zone from about 4 m to 12 m, right through the site centre.
This is the reference the reef is now built to. Site-metre footprint
x[−309, 671] y[−167, 223]; NAD83(2011) UTM 17N, NAVD88, which sits 0.11 m
above the bathymetry's datum here.

**Habitat.** FWC Unified Florida Reef Tract Map v2.2, thirty-one polygons
over the square: 20% spur-and-groove running south-west to north-east through
the middle at 5–10 m, 6% aggregate reef at 24 m, 28% sand seaward, 20%
seagrass and 18% rubble on the reef flat behind. Twenty-nine of the polygons
are classed under 10% coral cover.

**Monitoring.** CREMP 2024 tables: percent cover by group and by stony coral
species, colony densities, from eight fixed stations at Looe Key. Stony coral
here is Orbicella annularis complex, Porites astreoides, Millepora
alcicornis and Siderastrea siderea, at about 2.7 Siderastrea and 1 Porites
colonies a square metre. Octocorals are not surveyed at this site; their mix
comes from the photographs.

**Photographs.** 2,795 research-grade iNaturalist observations with photos
within 1.5 km, 195 species. Of the benthos: Gorgonia ventalina 80,
Palythoa caribaeorum 77, Antillogorgia 59, Millepora 18, Porites astreoides
16, Xestospongia muta 16, Siderastrea 8, Montastraea cavernosa 7. Eighty-seven
CC-licensed photographs of these are kept as the colour and form reference,
with attribution.

**From space.** Sentinel-2 true colour, the median of the eight clearest
scenes since 2023, at 10 m. It shows the whole square as it is: the pale
sand halo, the dark spur-and-groove band, the reef flat with its patch reefs
and seagrass. Used for the pattern of light and dark ground outside the
orthomosaic; its colours cannot be trusted through the water column.

**Scans.** The Smithsonian's coral type specimens are CC0 and downloadable
without an account through their 3D API; one Orbicella is in hand as a test.
They are dry skeletons, so they give geometry and not colour.

## What Looe Key looks like

From the photographs and the orthomosaic, not from a general idea of a reef:

- Most of the ground is pavement and low rock under turf algae, grey-brown
  to olive, with sand in the grooves. Six tenths of every frame.
- Standing over it, the gorgonians: purple sea fans a metre across, tan and
  olive sea plumes and rods. They are the silhouette of this reef.
- Palythoa mats, mustard yellow, sheeting over rock in the shallows.
- Stony coral as scattered heads: Porites astreoides mustard mounds a hand to
  a forearm across, Siderastrea grey domes, Orbicella lobed mounds up to a
  metre or two, Millepora blades on the crest. Rare enough that each one is
  an event.
- Barrel and tube sponges at depth, rust and brown.
- The spurs are 20–40 m long, 5–10 m wide, 2–4 m high, separated by sand
  grooves; the orthomosaic shows them as dark fingers with pale sand between.

## What changes

1. **Placement comes from imagery.** Inside the orthomosaic footprint, the
   5 mm image is classified into sand, pavement, coral head, gorgonian and
   sponge, and colonies are placed where the image has them. Outside it, the
   habitat polygons and the Sentinel pattern decide sand from reef, and the
   density inside reef is set to the CREMP numbers for that depth.
2. **Cover is the measured cover.** About 4% stony, 5–10% octocoral, 2–8%
   sponge, 4% zoanthid on the shallow reef, and the rest is ground that has
   to look like ground.
3. **Relief comes from the survey.** The 1 cm DEM replaces the 2 m grid where
   it exists, feathered in over 6 m at its edge.
4. **Colour comes from photographs.** Per species, from the reference set.
5. **The presentation renderer is Blender.** Isaac Sim keeps physics and
   sensors. Video and stills come from Blender Cycles on the box, from the
   same site files.

## The tools, in order

| tool | what it does |
| --- | --- |
| `tools/reference` | fetches the record above into `~/coral-city/reference/<place>/`, licences beside it |
| `tools/ground` | the 1 m heightfield with the survey merged in, habitat classes, colour and chart maps |
| `tools/terrain-flyover` | Blender on the box flies that ground dry; `uav terrain <place>` |
| `tools/benthos` | every colony standing on the surveyed seabed, from the 1 cm DEM and the 5 mm orthomosaic |

`benthos` is the placement engine. A colony is anything compact that stands
eight centimetres above the median of its 1.2 m surroundings and is not the
noise photogrammetry makes over textureless sand. Over the eight survey tiles
that finds 83,055 colonies: median 19 cm across and 17 cm tall, every one with
its colour from the orthomosaic. On a 50 m test square they cover 3.0% of the
ground; CREMP measured 3.4% stony coral at the shallow stations. Colour and
shape sort them, as a first guess the photographs refine, into 17,109 stony,
7,317 octocoral, 644 large heads and 57,985 low lumps of rock or Siderastrea.
The detector reads the tiles straight off the USGS server at 2 cm, which is a
quarter of the bytes of downloading them, and runs one process per tile.

What remains after this: outside the survey, colonies drawn to the CREMP
densities on ground the habitat map calls reef; scanned or sculpted colonies
with photographed colour placed on the list; water in Cycles; and the same
list written to USD for Isaac Sim.
