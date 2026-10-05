# The forum deck: outline and speaker notes

*Draft, 5 October 2026, for the Saudi Maritime & Logistics Congress (21–22 October).* One generic deck in English, about twelve minutes in a meeting. Each slide below has what it shows and, under **Note**, what is said over it. The notes go into the deck's speaker notes word for word once this outline is agreed.

Numbers marked *(pending)* come from dives still running on 5 October.

---

## 1. Title

**Shows:** iocean. *Rehearse the underwater job before the boat leaves.* A still from the pipeline film.

**Note:** We build a simulated ocean for planning underwater work. You fly the vehicle you will use, over the seabed where you will work, in the water you will meet. Before anyone books a vessel, you know whether the job works: what it covers, how long it takes, what it costs in battery, and what it does to the seabed around it.

## 2. The problem

**Shows:** three short lines.
- Underwater work is planned on paper and learned at sea.
- The vessel day is the expensive part, and it is where the plan meets the water for the first time.
- What goes wrong is predictable: the vehicle cannot turn onto the line, the current pushes it off the survey, the plume goes where nobody drew it.

**Note:** Every operator here has a story about a day at sea that went to finding out the plan didn't fit the water. A vehicle that couldn't hold the line in the current. A survey that came back with gaps. A dredging plume that reached the reef. None of these are surprises in hindsight. They come from physics that was knowable before the boat left. We put that physics where the planning happens.

## 3. What it is

**Shows:** four boxes feeding one dive: **the place** (real Saudi bathymetry and reefs), **the vehicle** (built from the maker's published sheet), **the water** (current, waves, turbidity), **the job** (inspect, survey, monitor, plant). Arrows run both ways between them.

**Note:** It is not a game engine with a submarine in it. It is a coupled ocean: each part acts on the others both ways. The thrusters' wash lifts sediment, the sediment clouds the camera, and the current carries the cloud onto the coral. The coral is solid, and a vehicle that hits it is stopped and the colony is counted. One flight gives you coverage, time, energy, and what the job did to the place, all together.

## 4. How it works

**Shows:** the designer screen. A place, things laid out on it (a pipeline, a dredger), a mission drawn over it, a vehicle chosen, a time estimate. Then the result page.

**Note:** You draw the job the way you would brief it: lay out what is on the seabed, draw the route or the area, pick the vehicle and the water. The platform plans the vehicle's path and flies it, with the vehicle's own controller, its own sensors and its own navigation errors. You get a result and a film. Change one thing, such as the vehicle, the current, the altitude or the controller, and fly it again. Everything else stays the same, so the difference is the thing you changed.

## 5. Every number says where it came from

**Shows:** a result line with its tag, for example *"452 m of 452 m seen — derived, from the simulator's truth"* and *"water clarity — measured, Overmans & Agusti 2020"*. The four kinds: measured, derived, chosen, assumed.

**Note:** This matters most to class and to regulators. Every figure we report carries what kind of figure it is and where it came from: measured in the field, derived by the simulation, chosen by a person, or assumed for want of data. A derived figure presented as a measurement is wrong even when the figure is right, so we never let one pass as the other. When you take a result into a permit application or a class review, you can follow every number back to its source.

## 6. Example: a pipeline inspected (offshore)

**Shows:** the pipeline film. A 452 m line from the fore-reef at 7.5 m down to 34 m, three free spans (1, 4 and 7 m), and a REMUS 100 following it at 4.5 m.

**Numbers:**
- all 452 m seen;
- all three free spans seen;
- 308 seconds;
- none of 1.1 million coral colonies struck;
- USBL navigation drift 0.16 m.

**Note:** This is a landfall: a pipeline coming ashore across a fringing reef. The seabed under it leaves it bridging three hollows, which are free spans, the thing an inspection is really for. The REMUS follows it on line-of-sight guidance with a USBL fix from the ship. Getting this right on the platform found four things that would have shown up at sea. A launch point the vehicle ignored. A torpedo that looped around points it couldn't turn onto. A depth controller that dived from the surface into the coral. Waypoints drawn in one format and read in another. Each was a day at sea, found at a desk.

## 7. Example: dredging beside a reef (ports)

**Shows:** the dredging film or plan view. A dredger 200 m off the reef, its overflow plume carried by a 0.15 m/s onshore current, and the colonies it settles on coloured by daily dose. Luna crosses the plume.

**Numbers (first flight; second pending):**
- 54 t lost at the overflow in 45 minutes (20 kg/s, assumed from the published range);
- 36.5 t settled;
- *(pending)* colonies past Erftemeijer's thresholds, and how far the plume reached;
- *(pending)* what Luna's turbidity sensor saw across it.

**Note:** Every port expansion on this coast dredges next to coral, and every permit asks the same question: where does the plume go, and what does it settle on? Here the dredger loses what a hopper dredger typically loses at its overflow. The current and the sea's own mixing carry it, and what lands on each colony is judged per day against the thresholds in Erftemeijer's review, which regulators use. You can move the dredger, change the current or the overflow rate, and see the reef's answer before the work starts. And you can plan the monitoring vehicle's route across the plume at the same time.

## 8. Example: reef restoration planned (Shushah)

**Shows:** the Shushah place (fitted to satellite and ICESat-2 depths, 1.28 m rms) and an outplanting and survey plan over its grid, with coverage.

**Note:** The kingdom's restoration programmes plant corals in hundreds of thousands. The hard part is not planting them. It is surveying them again on a cadence, cell by cell, and proving coverage. This is Shushah, built from public data and checked against satellite laser depths. A survey is planned over it, flown, and returned with coverage proof: which cells were seen, at what height, and what was missed.

## 9. Example: bring your vehicle (makers)

**Shows:** the four vehicles drawn this month from published sheets: REMUS 100, Seaglider, BlueROV2 Heavy and EdgeTech 2300. Beside them, our own hulls' drag measured in a numerical tow tank.

**Note:** A vehicle comes in as a package: hull, thrusters or fins, sensors, battery. It is built from the maker's own sheet. We drew these four in a month. Where no published hydrodynamic data exists, we measure it in a numerical tow tank and say so. For a maker, the offer is not another simulator. You have those. It is your vehicle flown in real Saudi water and seabed, on a client's actual job, with a result the client can audit. And the controller is yours: written against our SDK, deployed, tuned and flown.

## 10. How we tune it to yours

**Shows:** three inputs and three outputs.
- **In:** your site (bathymetry, survey, habitat map), your vehicle (sheet or package), your job.
- **Out:** the job flown with its numbers; the variations that matter (current, vehicle, altitude, controller), compared; the films.

**Note:** Everything you saw today was built for one example each. Yours starts from your data. If you have a multibeam survey of your site, the place is built on it. If not, we build it from satellite and public sources and say so in every number. Then we fly your job, vary what you are uncertain about, and give you the comparison.

## 11. Who it is for

**Shows:** a table.

| You are | You get |
|---|---|
| Offshore operator or contractor | inspection plans that fit the vehicle and the current, before mobilisation |
| Port or dredging contractor | plume and settling forecasts against permit thresholds, and the monitoring plan |
| Class society | results whose every number is traceable to its source |
| Vehicle maker | your vehicle demonstrated on Saudi sites and real jobs |
| Restoration programme | repeat-survey plans with coverage proof at scale |

**Note:** Point at the row that is the person in front of you, and go back to their example.

## 12. The ask

**Shows:** a pilot. One site, one job, one vehicle, a few weeks. What we need from you: the site data you have, the vehicle you would use, and ideally one past job to check our answer against.

**Note:** We are not selling a simulator licence. We are offering to rehearse one of your jobs. Give us a site, a vehicle and a job, and, if you have one, a past survey so we can show you how close we get. Name the next step: who sends what, and by when.

---

## Backup slides (questions we will be asked)

- **What is measured and what is not.** The Red Sea place in examples 6 and 7 is a constructed fringing reef: shaped like this coast, not surveyed. Shushah is fitted to satellite and ICESat-2 depths. Dredging rates are assumed from the published range, and doses are extrapolated to a day from the first hour.
- **How we validate.** The drag of the BlueROV2 Heavy was checked against Li et al.'s measured surge, within 10%. The REMUS coefficients were checked against Prestero's. We need one of your past jobs for your site.
- **What runs where.** *(to confirm: where the GPU servers sit and where a client's data is kept.)*
