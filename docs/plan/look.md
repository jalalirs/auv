# The look, end to end

From five places that photograph badly to five a reef scientist recognises.
One sequence, across all of them, in the order the work actually depends on.

**The principle, because it is the only thing that separates this from set
dressing.** A reef modelled from a general idea of a reef is wrong in every
particular and nobody can tell, because there is nothing to hold it against.
That was settled once already, on 2 September, when a grown reef putting 86%
coral cover on a site the survey says is 3.4% was thrown out
(`looe-key-reality.md`). The same rule now applies to the light: every photon
and every colony traceable to something somebody measured, or it does not go
in.

**The target.** A frame from a dive at Looe Key laid beside the USGS
photograph of the same square metre, and a reef scientist cannot say which is
the render. Then the same machinery carrying the other four.

---

## Where this starts

Five places, published, and what each of them actually is:

| | what it is | what it has behind it | what it looks like now |
| --- | --- | --- | --- |
| **looe-key** | Florida Keys fore reef, spur-and-groove | 5 mm orthomosaic, 1 cm DEM, 10.5 bn point cloud, CREMP cover since 1996, 87 licensed photographs | blue fog, no reef visible in any frame |
| **al-fahal** | Red Sea fringing reef, 3 km, where everything is flown | Sentinel-2, derived depths, v2 ground colour | bleached cream blobs, visible water-box seam, the edge of the world |
| **kaneohe** | Oʻahu barrier and patch reefs | NOAA topobathy lidar | the best of the five, and still plastic |
| **red-sea** | fringing reef off the Saudi coast | Sentinel-2 | rubble through a blue filter, no colour at all |
| **thuwal-deep** | 519–638 m off KAUST | measured synthesis | a flat blue rectangle, and black in every other frame |

And what is wrong, in one line each, because the diagnosis decides the order:

**There is no optical water model.** None. `hydrodynamics.py` computes density
for buoyancy and its own header admits absorption and backscatter are "the hard
part" and skips them. What you see is whatever fog the scene shipped with.

**Every colony is one flat colour.** `UsdPreviewSurface`, `diffuseColor`, one
RGB triple, `roughness 0.82`, `subdivisionScheme = "none"`. No albedo map, no
normal, no roughness, no AO, no UVs, no subsurface. Under a path tracer a flat
diffuse surface is a plastic blob, which is exactly what the frames show.

**There is no light at depth.** No vehicle lights, so the deep place is black
and the shallow ones have only a sun nobody tuned.

Ground and geometry are fine. Everything between the ground and the camera is
missing.

---

## 1 · A frame you can compare

`tools/look`, and a fixed viewpoint per place.

Before anything changes. `tools/fly-over` flies a path and hands back whatever
it passed; two runs are not comparable and neither is a before and after. Every
step below is a judgement about an image, and a judgement made against memory
is not a judgement.

So: named viewpoints — at the mission site, on the bottom looking along it,
mid-water looking down, and one at the site edge — rendered identically in
every place, written with the parameters that made them stamped in the corner.
One sheet, five places, four views.

**Done:** the same command, twice, a week apart, produces images that differ
only where somebody changed something.

## 2 · Water that absorbs and scatters

`coral/optics.py`, and the scene's medium.

The one that changes all five places at once, and the one everything after it
is judged through. Absorption and scattering kept apart, because they do
opposite things: absorption takes light away, scattering moves it sideways.
One fog density conflates them, which is how the current frames manage to have
no contrast *and* no glow.

  **Spectral.** `a(λ)` and `b(λ)` per band, not a grey coefficient. In clear
  ocean red runs about 0.4 per metre and blue about 0.02 — a twentyfold ratio,
  and that ratio *is* the underwater look. It is why Al Fahal's red smudges
  are the only colour left at ten metres.

  **Jerlov types** as the parameterisation — oceanic I to III, coastal 1C to
  9C — with the measured coefficients, so "clear Red Sea" and "Florida Keys in
  August" are selections rather than adjustments.

  **Henyey–Greenstein, g ≈ 0.92.** Seawater scatters hard forward. That is the
  veiling glare around anything bright and the most recognisable cue there is.

  **Driven by what a reef programme measures** — chlorophyll-a, CDOM,
  suspended sediment. Then the aesthetic and the science are one system, and
  *what does the site look like during a bloom* becomes a question this can
  answer. Nothing bought off a shelf can say that.

**Done:** the same reef at Jerlov I and Jerlov 5C, side by side, and the
difference is the one a diver would describe.

## 3 · The surface, and the light through it

Caustics from the wave spectrum that already exists in the physics — animated
from it, not a looping texture, because a loop is a lie that a scientist spots
in four seconds. Volumetric shafts, which fall out of a real medium and cannot
be faked convincingly without one. Snell's window. Sun by latitude, time of day
and depth, split from skylight.

**Done:** a frame at three metres at noon, and one at fifteen at four o'clock,
and nobody has to be told which is which.

## 4 · Lights, and what they light up

Photometric cones from the vehicle's own package, and **backscatter** — light
hitting particulate right in front of the port. That single effect is the
defining look of every piece of ROV footage ever shot, and without it lights
read as theatre spots. Marine snow in the near field, at a density the water
type sets.

This is also the step that makes the deep place possible at all: at 600 m
there is no sunlight, and everything seen is seen by a lamp the vehicle
carries.

**Done:** Thuwal Deep stops being a black rectangle.

## 5 · The camera is a camera

Physically-based sensor with **auto-exposure**, because an ROV camera has one
and the way it hunts is half of why real footage looks the way it does. Dome
port distortion, chromatic aberration, vignette. ACES tonemapping and a grade.

Placed here rather than first on purpose: an auto-exposure over a wrong medium
tunes itself to the wrong thing. Some of Al Fahal's washed-out cast is
certainly this, and it cannot be told apart from the water until the water is
right.

**Done:** no frame in the sheet is blown out or crushed, in any of the five.

## 6 · Coral is tissue over skeleton

The materials, on the geometry that already exists.

  **Subsurface scattering.** Coral is translucent tissue over white aragonite.
  This is why living coral glows and bleached coral does not, and a diffuse
  surface physically cannot produce it. It is the single biggest reason Al
  Fahal's colonies read as dead.

  **Fluorescence.** GFP-like proteins re-emit green and orange under
  blue-shifted deep light. It is most of why reef footage looks otherworldly,
  and it is measurable, so it is allowed in.

  **The rest of PBR** — albedo, roughness, normal, AO, and displacement at
  corallite scale.

**Done:** the same colony, same light, before and after, and the second one is
alive.

## 7 · Looe Key is rebuilt from the photograph

`tools/from-the-orthomosaic`.

**The centre of this plan.** Everything above is machinery; this is the step
where the reef stops being invented. The USGS flew a five-camera sled over the
fore reef in July 2022 and published, public domain: an 850 × 160 m
orthomosaic at **5 mm**, a 1 cm digital elevation model, and a **10.5 billion
point cloud**. It covers the spur-and-groove from 4 m to 12 m, straight
through the site centre, and nothing has ever been built from it.

So it is not modelled. It is rebuilt:

  **The ground is the DEM.** One centimetre, with the metre-scale spur relief
  the 2 m bathymetry rounds off. The site's own heightfield keeps the square
  outside the strip and is feathered into this inside it.

  **The colour is the orthomosaic.** Five millimetres, so at half a metre of
  altitude the camera is looking at real detail instead of a stretched
  satellite pixel.

  **The colonies are the colonies.** Segment the orthomosaic and each patch is
  a colony somebody photographed — where it is, how big, what colour, what
  species, on a reef where the survey already says there should be about 2.7
  *Siderastrea* and 1 *Porites* a square metre.

This is what "real" means and it costs nothing but the work: the data is
public, licensed, and already fetched by `tools/reference`.

**Done:** a render of a named square metre beside the USGS photograph of that
square metre, and the difference is the water, not the reef.

## 8 · The library, from what Looe Key taught

Only now, and taught by a measured reef rather than by taste.

  **Stony coral**: *Orbicella annularis* complex, *Porites astreoides*,
  *Siderastrea siderea*, *Montastraea cavernosa*, *Millepora alcicornis* —
  the four species the survey actually found, plus the crest's fire coral.
  Geometry from the Smithsonian's CC0 type specimens, which are dry skeletons
  and give form; colour and tissue from the orthomosaic and the 87 licensed
  photographs.

  **Octocorals, which are the silhouette of this reef and are missing
  entirely**: *Gorgonia ventalina* sea fans a metre across, *Antillogorgia*
  plumes and rods. Eighty of the photographs are of these. They are the most
  visible thing on a Caribbean reef and there is not one in the model.

  **Sponges**: *Xestospongia muta* barrels, tube sponges, rust and brown.

  **The mats**: *Palythoa caribaeorum*, mustard, sheeting over rock.

  **And the six tenths of every frame that is not coral at all** — pavement
  and low rock under turf algae, grey-brown to olive, with sand in the grooves.
  Getting the *bare* right matters more than getting the coral right, because
  it is most of the picture.

**Done:** a frame of the reef flat with no coral in it that still reads as the
Florida Keys.

## 9 · It moves, and something lives in it

Gorgonians and soft coral flex in the current — and the current is already in
the physics, so this is a connection rather than an animation. Then fish:
schools, and a few large individuals.

An empty reef reads as dead however good the coral is, and every frame in this
document is empty.

**Done:** ten seconds of video where nothing is being demonstrated and it is
still worth watching.

## 10 · Ground as fine as the camera

Where there is no orthomosaic — which is four of the five places — habitat-class
detail textures at several scales, **height-blended** rather than mixed, sand
ripples as real displacement oriented by the current, and the satellite colour
demoted to a low-frequency tint. At half a metre of altitude a 1 m satellite
pixel is the smear in the Al Fahal frames, and no amount of coral fixes it.

**Done:** a frame from a vehicle sitting on the bottom, on sand, nowhere near
a colony, that is worth looking at.

## 11 · Al Fahal, and the question of the Red Sea pair

Al Fahal is the site everything is flown in, and it gets the library placed at
the cover its own evidence supports. Its water is Jerlov oceanic, not Florida
coastal, and the species are Indo-Pacific — *Acropora*, *Porites*,
*Pocillopora* — so the library grows a Red Sea half.

Also to be settled here rather than carried: **`red-sea` and `al-fahal` may be
the same place twice.** One is "a fringing reef off the Saudi coast" and the
other is a fringing reef off the Saudi coast. If the first is a generic built
before the second was measured, it should be retired rather than dressed, and
the effort spent once.

**Done:** the water-box seam and the edge of the world are gone, and the
colonies are Indo-Pacific.

## 12 · Kaneohe

The best-looking of the five and a different morphology: patch reefs standing
on sand in a barrier lagoon, not a fringing slope. Hawaiian species, turbid
lagoon water rather than oceanic — and the lidar is good, so the geometry is
already there.

**Done:** the patch reefs read as patch reefs, and the water reads as a lagoon.

## 13 · Thuwal Deep is a different world

Six hundred metres. No sunlight, no coral, no algae — none of the library
applies and none of the aesthetic above survives the trip down.

  **Everything is seen by lamp**, so step 4 is the whole of the look here:
  a cone, backscatter, and darkness outside it.

  **The ground is soft sediment** — bioturbated, with tracks and burrows and
  the occasional dropstone.

  **The fauna is deep Red Sea**: whip corals, glass sponges, holothurians,
  and the brine pools that make this basin worth a mission at all.

  **The marine snow is the atmosphere**, not an effect.

And it needs a mission, because it has never had one: the glider section in
`missions/section-thuwal.json` exists as a file and has never been flown.

**Done:** a minute of lamp-lit video at 600 m that looks like the abyss and
not like a dark reef.

## 14 · All five, one sheet

The step from 1, run again at the end. Twenty frames, five places, four views,
with the water type, the depth, the time of day and the source of every asset
stamped on them.

**Done:** it goes in front of somebody at KAUST without an apology.

---

# How this is kept honest

**Nothing is judged from memory.** Step 1 is first because every other step is
a claim about an image, and the only way to hold anybody to it is the same four
frames before and after.

**The water is before the assets, and this is not negotiable.** Buying
photogrammetry colonies and then looking at them through the fog in these
frames is spending money to photograph fog. Every step from 6 onward is judged
through the medium built in 2 to 5, so the medium is built first.

**Nothing invented is allowed in.** Colonies come from scans, cover from
surveys, colour from photographs, water from measured coefficients. Where a
number cannot be sourced it is a parameter with the uncertainty written next to
it, not a value somebody liked. This is the rule that was bought the hard way
in September and it applies to light exactly as it applied to cover.

**Looe Key is the calibration and the others are the test.** It is the only one
of the five with ground truth at the scale of a camera frame, so it is where
"is this right" can be answered rather than argued. The other four are where it
is found out whether the machinery generalises to a place with no orthomosaic —
which is every place a customer will bring.

**Thirty metres is the target, not three kilometres.** That is all a camera
ever sees underwater. A 3 km site cannot be hand-authored and does not need to
be; the sphere around the vehicle is the only part anybody judges.

**What would show this plan is wrong:** a reef scientist looking at the step 7
comparison and pointing at the render immediately; the step 2 water looking
correct at Looe Key and wrong at Al Fahal, which would mean the parameterisation
is fitted rather than physical; or the whole thing landing and a dive still
being unwatchable because the camera is somewhere nobody would put one.
