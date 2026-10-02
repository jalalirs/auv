# r6, item 0: what has been done before

October 2026. Four searches ran in parallel: simulators, fish, cables, and
coral/sediment/flow. Commercial products publish marketing, not
specifications, so much of what they do is marked unknown rather than guessed.
Numbers worked out here, not read from a source, say *derived*.

## The verdict

**No simulator found, academic or commercial, couples the vehicle's own wash
into a water field that the fish, the coral, the sediment and the tether all
feel.**

Two things are missing everywhere:

- The water. In every system the current is something that pushes the vehicle
  and is never changed by it.
- The coral. No system has coral that bends or breaks.

Every part of the coupled engine exists somewhere as a paper or a library. None
of them has been put together.

The closest systems, and what each lacks:

| System | What it has | What it lacks |
|---|---|---|
| **Stonefish** + Stonefish-Boids (GPL-3.0, Bullet) | hydrodynamics from the hull's geometry; propellers drawn at their real speed; lumped-mass tether; contact with friction; four sonars; boid fish that keep a fixed distance from the ROV | water the vehicle stirs; fish behaviour beyond a repulsion radius; living coral; tether failure; sediment; photoreal rendering |
| **GRi VROV** (commercial pilot trainer) | "interactive tether collision and dynamics"; contact forces; multibeam | coupled water; marine life; coral (none in public material); turbidity is a global slider, not something the thrusters stir up |
| **Oceaneering on CM Labs Vortex** | cables and TMS; a published study shows loops forming with "snagging risk" | no failure logic; the rest is not public |
| **HoloOcean 2.0** (Unreal 5.3) | best rendering (Lumen); Fossen dynamics within 2% of real AUV data; sonars | tether, fish, coupling |
| **OceanSim** (Isaac Sim, our base) | fast GPU camera and imaging-sonar rendering | perception only, nothing else |
| **FishGym / Aquarium** | the only genuine two-way fluid–body coupling | not real-time vehicle simulators; Aquarium is 2D |

The only reef "digital twin" near our buyers is **digiLab–KAUST for KCRI**
(July 2025): a data and AI platform over 100 ha, with video monitoring and a
chat interface. It holds data rather than simulating physics, so it complements
us rather than competing.

## The full simulator table

Y yes · N no · P partial · ? not verifiable from public material.

Columns:

1. 6-DOF hydrodynamics
2. thrusters drawn spinning
3. flow field the vehicle writes into
4. fish with behaviour
5. fish react to the vehicle
6. coral that bends or breaks
7. dynamic tether
8. snag or entanglement
9. sediment from thrusters
10. contact forces
11. sonar
12. real-time
13. photoreal

| System | Base | Licence | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Stonefish (+Boids) | Bullet | GPL-3.0 | Y | Y | N | P | P | N | Y | ? | N | Y | Y | Y | P |
| HoloOcean 2.x | UE5.3 | open | Y | ? | N | N | N | N | N | N | N | Y | Y | Y | Y |
| OceanSim | Isaac Sim | custom | N | ? | N | N | N | N | N | N | N | ? | Y | Y | Y |
| MarineGym | Isaac/PhysX | MIT | Y | ? | N | N | N | N | N | N | N | Y | N | Y | P |
| DAVE | Gazebo | Apache-2.0 | Y | P | N | N | N | N | P | N | N | Y | Y | Y | N |
| UUV Simulator | Gazebo | Apache (archived) | Y | Y | N | N | N | N | P | N | N | Y | ? | Y | N |
| MARUS | Unity | Apache-2.0 | P | ? | N | ? | ? | N | ? | N | N | Y | Y | Y | P |
| UNav-Sim | UE5/AirSim | open | P | ? | N | N | N | N | N | N | N | P | P | Y | Y |
| LOTUSim | Gazebo+Unity | EPL-2.0 | Y | ? | N | ? | ? | ? | ? | ? | ? | Y | ? | Y | P |
| BlueSim | Godot | GPL-2.0 | P | ? | N | N | N | N | ? | N | N | Y | Y | Y | P |
| FishGym/Aquarium | LBM / 2D NS | academic | P | – | **Y** | N | N | N | N | N | N | P | N | N | N |
| GRi VROV | proprietary | commercial | Y | ? | ? | ? | ? | ? | **Y** | ? | P | Y | Y | Y | P |
| Oceaneering/Vortex | Vortex | commercial | Y | ? | ? | ? | ? | ? | Y | P | ? | Y | Y | Y | P |
| Fugro DeepWorks | proprietary | commercial | Y | ? | N | ? | ? | ? | Y | ? | ? | Y | ? | Y | P |
| Tree-C SENTIO | proprietary | commercial | Y | ? | ? | ? | ? | ? | Y | ? | ? | Y | Y | Y | P |
| ProteusDS | lumped-mass FE | commercial | Y | N | N | N | N | N | Y | P | N | Y | N | N | N |
| OrcaFlex | FE lines | commercial | P | N | N | N | N | N | Y | P | N | Y | N | N | N |

Also checked, with nothing to add: URSim, SubSim, PaleBlue, VMAX, ROVsim,
Kongsberg K-Sim, Tecnalia, Isaac Lab marine. The reef "digital twin" papers
on arXiv are ocean models, not robot simulators.

## What we adopt, system by system

### Fish (r6 item 5)

- **Swimming and schooling:** Calovi 2018 burst-and-coast, with Lei 2020's
  one or two most influential neighbours. There is reference code at
  epfl-mobots/burst-and-coast.
  - Every value is for a 31 mm tetra in a lab tank: kick about 0.5 s; about
    4.5 BL/s while active; glide decay 0.8 s; heading noise 0.35 rad;
    alignment out to about 3 BL; attraction out to 6–7 BL; repulsion under
    about 1 BL.
  - So everything is held in body lengths and rescaled per species sheet. That
    rescaling is *assumed*.
- **Checking the school:** Tunstrøm 2013's order parameters. Polarised is
  Op > 0.65; milling is Or > 0.65; swarm is both under 0.35.
- **Fleeing the vehicle: Hein 2018's looming rule,** measured on twelve wild
  reef species and 82–98% accurate out of sample.
  - The fish flees on how fast the vehicle grows in its view.
  - That is held back by how big the vehicle already looks, and by how much of
    the view its neighbours fill.
  - It first steers away for 200–300 ms, then heads for shelter.
  - This replaces the flight-distance threshold in `fishmind.py`.
- **Calibrating flight:**
  - Cai 2025 (WHOI's CUREE AUV over reefs): fish head for shelter as the
    vehicle comes; strong reactions under 1.6 m altitude, muted at 1.6–4.5 m.
  - Reef flight distances: parrotfish 0.03–3.7 m (Gotanda); snapper over 3 m
    (Feary); fished sites about 1.4 m more than reserves
    (Januchowski-Hartley).
  - Fished against protected becomes a wariness setting per place.
- **Checking count bias:**
  - 57% of fish react to an ROV against 11% to a crewed submersible (Laidig
    2013).
  - A bubble-free rebreather diver counts up to 2.6 times more fish than a
    scuba diver at fished sites (Lindfield 2014).
- **The mind:** Tu & Terzopoulos's intentions, chosen by scoring each
  behaviour every tick as Subnautica does. That is what `fishmind.py` already
  does.
- **Day and night:**
  - damselfish stay in their coral all night and "sleep-swim" (Goldshmid
    2004);
  - a parrotfish's night cocoon costs 2.5% of its daily energy (Grutter 2011);
  - home ranges: Welsh & Bellwood 2012; Green 2015.
- **Data to fit or check against:**
  - Fish4Knowledge: *Dascyllus* tracks on a Taiwan reef.
  - Lilkendey 2024: 3D stereo tracks of Red Sea surgeonfish at Eilat, on
    GitHub.
  - WildFin 2026: CC-BY.
  - idtracker.ai.
- **Genuinely missing in the world:**
  - interaction parameters measured on wild reef fish;
  - any public dataset pairing a vehicle's track with fish tracks;
  - a model that drives day and night from internal drives.

### Water and thruster wash (item 3)

A jet per thruster, added on top of the background current:

| Part of the jet | Rule |
|---|---|
| Speed leaving the thruster | actuator disk √(2T/ρA); or Hamill k = 1.33 (Fuehrer & Römisch's k = 1.59 is theory) |
| Core | Vmax/V0 = 1.107 − 0.184·x/Dp, out to 2–3 Dp |
| Beyond the core | Verhey 2.78·D0/x |
| Near the bed | Stoschek's corrected C and b |
| Across the jet | exp(−22.2 (r/x)²) |
| Spread | 13–15° |

- **A T200 at 16 V:** 76 mm propeller, 5.25 kgf. The jet leaves at about
  4–4.7 m/s and is about 0.7 m/s at 1 m (*derived*).
- **Precedent:** arXiv 2607.07139 used this kind of model for an 8-thruster
  ROV. Checked against PIV, it fitted the jet's centreline with R² 0.99.
- **Optionally,** the jets feed a coarse stable-fluids grid in Warp so wakes
  persist. Warp ships fluid examples.

### Sediment and clarity (item 8)

- **When sand moves:** Soulsby–Whitehouse critical Shields stress. For 0.2 mm
  sand that is about 0.15 Pa (*derived*); mud is 0.07–0.12 Pa.
- **Stress the jet puts on the bed:** τ = ρ·Cf·u², with Cf 0.002–0.01
  (*assumed*).
- **Erosion:** E = M(τ/τc − 1), with M 1e-4 to 1e-3 kg m⁻² s⁻¹ (*assumed*, varies
  by site).
- **Settling:** Ferguson–Church. 0.2 mm sand about 2.3 cm/s; 20 µm silt about
  0.35 mm/s (*derived*).
- **Plume:** carried on a concentration grid moving with the flow. Measured
  plumes slump into bottom-hugging currents, with only 2–8% rising more than
  2 m (Sci. Adv. 2022).
- **Visibility:** about 4.8/c, where c is beam attenuation (Zaneveld & Pegau,
  under 10% error). The camera's contrast falls as exp(−c·d) per colour.
  Concentration to c is per site (*assumed*).

### Coral (item 6)

- **Torn off:** Madin & Connolly 2006's colony shape factor. The reef rock
  under a colony is about ten times weaker than its skeleton, so the rock is
  usually what gives.
- **Broken:** branching *Acropora* at 8.6 ± 3.0 MPa slowly and 20.8 ± 5.0 MPa
  in an impact. Massive *Porites* barely breaks. Marshall 2000 ranks species by
  how they break.
- **Sea fans:** a bending stick that reconfigures in flow, with Vogel exponent
  about −0.7 (*assumed*; the moduli could not be checked). They feed best at
  10–15 cm/s.
- **Smothering:** harm starts at about 10 mg cm⁻² d⁻¹ and is severe above 50
  (Erftemeijer 2012; Tuttle & Donahue 2022).
- **Contact damage:** of divers' contacts with the reef, 4.1% break coral,
  rising to 74% damage when live branching coral is hit.
- **Polyps:** large-polyp corals mostly open at night (Sebens & DeRiemer
  1977).

### Tether (item 7)

- **Engine:** a Newton rod. Newton is NVIDIA's physics engine on Warp
  (Apache-2.0). It replaced `warp.sim`, which was removed in Warp 1.10.
  - It already has a cable solver with bending, twist and contact.
  - We add per-node weight and Morison drag against the water field, and
    pay-out by adding segments at the reel.
- **Checking against:**
  - **Genoa/DFKI's 2025 Scientific Data set:** a BlueROV2 with its tether's
    shape motion-captured and the drum's tension measured, CC-BY. This is the
    primary check.
  - MoorDyn (BSD-3) as a reference on the CPU.
- **Blue Robotics Fathom tether:** 7.6 mm, 0.043 kg/m, neutral in fresh water,
  155 kgf breaking, 200 mm minimum bend.
- **The dive fails when any one of these holds:**
  1. **Too tangled to reach:** the tightest path the tether could take,
     keeping its windings round obstacles, is longer than the tether paid out
     (REACT, DFKI 2026).
  2. **Held:** the tether is in contact, the pull at the vehicle is near the
     thrusters' limit, and the vehicle makes no progress for a set time.
  3. **Broken:** the tension passes the breaking load, or the tether is bent
     tighter than its minimum radius.
  - Winding number and contact count are logged as how tangled the tether is,
    but never fail a dive on their own.
- **Not usable as our engine:** MoorDyn has no rock contact; Stonefish's cable
  has no drag; OrcaFlex and ProteusDS are paid and offline. They are
  references only.

### Towing (item 11)

- **Depth against speed and cable out:** EdgeTech's published curves for its
  4125 towfish. With 50 m of Kevlar cable it flies at about 35 m at 2 kn and
  about 10 m at 6 kn. These are modelled, not measured.
- **Height:** the 2300 should fly at 10–15% of its sonar range above the
  bottom. It is rated to 3000 m.
- **Steady tow:** WHOI Cable (GPL-3.0) is the offline reference.

### Light (item 9)

- **Sun:** NREL SPA.
- **Water:** spectral attenuation by Jerlov water type, from Solonenko &
  Mobley 2015. Kd(490) runs from 0.035 m⁻¹ in clear oceanic water to 0.15–0.35
  m⁻¹ on the coast.
- **Tank:** about 8–10 h at full light, with ramps (*assumed*; hobbyist
  practice).

## Sources

**Simulators**

- [Stonefish](https://arxiv.org/pdf/2502.11887) ([code](https://github.com/patrykcieslak/stonefish))
- [HoloOcean 2.0](https://arxiv.org/html/2510.06160v1)
- [HoloOcean coastal generation](https://arxiv.org/abs/2609.10484)
- [OceanSim](https://arxiv.org/pdf/2503.01074)
- [MarineGym](https://arxiv.org/abs/2503.09203)
- [DAVE](https://github.com/Field-Robotics-Lab/dave/wiki/)
- [LOTUSim](https://arxiv.org/pdf/2607.03072)
- [Simulator review 2025](https://arxiv.org/abs/2504.06245)
- [GRi VROV](https://grisim.com/products/vrov-virtual-remotely-operated-vehicle/)
- [Oceaneering on Vortex](https://cm-labs.com/en/resource/oceaneering-inc-leverages-vortex-studio-to-produce-innovative-subsea-simulations/)
- [Fugro DeepWorks](https://www.offshore-energy.biz/uk-fugros-deepworks-simulator-models-complex-sea-currents/)
- [ProteusDS](https://proteusds.com/proteusds/)
- [FishGym](https://arxiv.org/abs/2206.01683)
- [digiLab–KAUST](https://insidehpc.com/2025/07/digilab-and-kaust-in-ai-digital-twin-coral-restoration-partnership/)

**Fish**

- [Calovi 2018](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005933)
- [Lei 2020](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007194)
- [Tunstrøm 2013](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1002915)
- [Heras 2019](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007354)
- [Hein 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6275531)
- [Cai 2025](https://arxiv.org/html/2506.11335v1)
- [Laidig 2013](https://spo.nmfs.noaa.gov/content/reactions-fishes-two-underwater-survey-tools-manned-submersible-and-remotely-operated)
- [Lindfield 2014](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.12262)
- [Sward 2019](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2019.00134/full)
- [Gotanda 2009](https://link.springer.com/article/10.1007/s00265-009-0750-5)
- [Feary 2011](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0022761)
- [Lilkendey 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10909578/)
- [Fish4Knowledge](https://homepages.inf.ed.ac.uk/rbf/Fish4Knowledge/GROUNDTRUTH/BEHAVIOR/)

**Cables**

- [MoorDyn](https://moordyn.readthedocs.io/en/latest/inputs.html)
- [Newton](https://github.com/newton-physics/newton)
- [REACT](https://arxiv.org/abs/2507.10204)
- [Entanglement definitions](https://arxiv.org/abs/2402.04909)
- [Rajan 2016](https://eprints.whiterose.ac.uk/id/eprint/90764/)
- [ROV + tether dataset](https://www.nature.com/articles/s41597-025-06347-0)
- [Fathom](https://docs.bluerobotics.com/fathom/)
- [EdgeTech 4125 towing](https://igp.de/manuals/Towing%20Characteristics%20for%204125%20Telemetry%20Towfish%20-%20Rev%201.pdf)
- [WHOI Cable](https://github.com/jgobat/cable)

**Flow, sediment, coral**

- [Hamill/Stoschek jets](https://www.dhigroup.com/upload/publications/coastsea/Stoschek_2014.pdf)
- [ROV wake model](https://arxiv.org/abs/2607.07139)
- [T200](https://bluerobotics.com/store/thrusters/t100-t200-thrusters/t200-thruster-r2-rp/)
- [Shields thresholds](https://www.hec.usace.army.mil/confluence/rasdocs/d2sd/ras2dsedtr/6.6/model-description/critical-thresholds-for-transport-and-erosion)
- [Plumes](https://www.science.org/doi/10.1126/sciadv.abn1219)
- [Visibility](https://pubmed.ncbi.nlm.nih.gov/19471421/)
- [Madin & Connolly](https://pmc.ncbi.nlm.nih.gov/articles/PMC3464260/)
- [Marshall 2000](https://www.int-res.com/abstracts/meps/v200/meps200177)
- [Erftemeijer 2012](https://pubmed.ncbi.nlm.nih.gov/22682583/)
- [Coral stressor thresholds](https://github.com/ljtuttle/coral_stressor_thresholds)
- [Jerlov Kd](https://opg.optica.org/ao/abstract.cfm?uri=ao-54-17-5392)
