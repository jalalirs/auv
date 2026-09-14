# The list

How we work now: one item at a time. I say what is next, you approve it, we build
it, we check it off. Nothing gets started because it seemed related to something
else.

Each item says what it is, why it is in this order, and **what has to be true to
call it done** — because "done" has meant too many different things today.

---

## 1. The world

A reef you would believe. Large extent, real seabed, coral, marine life that
moves, and underwater rendering that looks like water rather than grey fog:
light absorbed by wavelength with depth, caustics on the seabed, particulate
scatter, a surface seen from below.

Whether we import an existing environment or build one depends on what is
actually available and licensed for commercial use. That is being checked now,
not guessed at.

**Done when:** a dive opens in a reef of at least a few hundred metres, the
seabed is real terrain rather than a plane, coral and fish are present, fish
move, and a frame from the chase view is one you would put in front of somebody
without apologising for it.

---

## 2. Controllers, and the first two: manual and the hold

A dive is flown by a controller, and controllers are the product. A person
writes one — logic, a model, a policy — for a vehicle, deploys it to the
platform, and flies with it; tunes what it exposes while the dive runs; trains
what has to be trained against the simulator and deploys the result. The
console is a real cockpit around that, not a viewer with arrow keys.

What exists already and is kept: an autonomy stack is a container pinned by
digest, admitted against the vehicle's topic contract, talking ROS 2 to the
simulator. That is the deployment path for a person's controller. What is
missing is everything around it.

**The framework, in the runtime.** One interface for every controller: observe
the vehicle's state and sensors, return a command in the terms the vehicle
accepts — a body wrench, or thruster commands — and declare the parameters it
exposes, each with a range, so the console can show them and a person can move
them mid-dive. Built-in controllers run in the runtime itself; a person's runs
as a stack over ROS 2 through the same interface. The vehicle's contract says
which command kinds it accepts and which sensors it carries, so the platform
can say which controllers a vehicle supports before a dive is admitted: the
BlueROV2 accepts a wrench and thruster commands; a REMUS needs control surfaces
the runtime does not model yet and supports none.

**The first two controllers.** Manual: keys and a gamepad mapped to a wrench,
with rate and deadband tunable, the controller a person flies with today.
Hold: station-keeping on depth, heading and position, the controller every
dive begins under so that a vehicle sits still where it was put, and which
lets go the moment another controller commands. Autopilots for depth,
heading and altitude are the hold's parts and come with it, so manual flying
can be assisted the way a real ROV's is.

**Done when:** a dive opens with the hold engaged and the vehicle sits within
a few centimetres for a minute; the console shows which controller is flying
and its parameters, and moving one changes the behaviour live; taking the
keys switches to manual cleanly and releasing them returns to the hold.

*Where it stands:* done, and verified on a live Looe Key dive over the same
socket the application uses (3 September): the hold kept 4.081 m for a minute
with no measurable spread; six seconds of W took the vehicle three metres
ahead under manual and letting go returned it to the hold within two
centimetres; moving depthKp on the socket changed it live; "hold here" moved
the station. The framework is `services/sim-runtime/coral/controllers`:
Observation, Command, Parameter, Controller; Pid; Autopilots and the hold;
manual with assist; a stack over ROS 2; and the Helm that decides who has the
vehicle. Six tests run the real integrator headless.

Three things the physics taught us on the way, all now in the code: the
BlueROV2's thrusters sit above and ahead of its centre of gravity, so surge
pitches it nose-down and heave pitches it too, and with two centimetres
between its centres a hard push turns it over — so the helm guards attitude,
limiting any wrench to a share of the hull's righting moment (tunable,
default 0.35, about a twenty-degree lean at the stop), and the hold sizes its
loops to the authority that leaves. The allocator now commands exactly the
axes the thrusters can reach and leaves pitch to the hull rather than
trading heave against it. The hold's loops are in accelerations, with the
model's own net buoyancy fed forward as trim, so the same gains mean the same
thing on every vehicle. Left for the fleet item: the catalogue's two-centimetre
righting arm and vertical-thruster offset are literature values; a measured
BlueROV2 leans less than this model does, and a source that measured it
should replace them.

---

## 2b. The controller SDK, and deploying your own

A Python package a person installs to write a controller for a vehicle:

- a vehicle description generated from the catalogue — its command kinds,
  thrusters, sensors, topics — so a controller written against it is checked
  before it is deployed;
- a base class with the same interface the runtime uses, and a decorator
  that declares tunable parameters with ranges;
- a way to run it live against a dive over ROS 2, and a way to run it fast
  and headless against the simulator for training — a gym-style environment
  over batch dives, with the task's score as the reward when a task is set;
- one command that packages the controller as an image, publishes it as an
  autonomy stack, and grants it to the person's institution.

What a person trains and deploys — a learned policy — goes through exactly
the same path as a hand-written one; the platform does not care which.

**Done when:** a controller written against the SDK for the BlueROV2 flies a
dive from the console, its parameters can be moved live, and the same code
runs headless against a batch dive with a score coming back.

*Where it stands:* done, and verified on the box (3 September). The package
is `packages/sdk-python` (`pip install -e 'packages/sdk-python[tank,dev]'`,
command `coral-city`): a `Controller` base with the runtime's own
Observation, Command and declared parameters; vehicle descriptions generated
from the catalogue with thrusters, sensors, topics and capability, and a
`check` that refuses a controller for a vehicle it cannot fly; a `Navigator`
that turns pressure, attitude and DVL velocity into an observation, used by
the live node and the tank alike; a headless `Tank` on the runtime's physics
with gym-style `reset`/`step` and tasks that score in [0, 1] (`HoldStation`,
`ReachDepth`); a ROS 2 node that declares each tunable as a parameter with a
range; a platform client; and `coral-city deploy` — image on ros:jazzy with
the SDK inside, pushed, registered by digest as the institution's autonomy —
followed by `coral-city dive`. The example station hold scores 1.0 in the tank
through its sensors, flew a batch dive on Looe Key (943 commands in ten
seconds), and on an interactive dive the console channel showed it flying
with its eight tunables beside the runtime's, and moving `depthM` took the
vehicle from 4.10 m to 5.10 m. The runtime side: the bridge now puts an
attitude on the IMU and reads the stack's ROS parameters through its
parameter services, so the console's stack panel is any rclpy node's
parameters — nothing of ours is needed on the stack's side.

Three follow-ups, none blocking: the API has no versions for autonomy, so a
rebuilt controller is registered as `slug-label` and `dive --stack slug`
takes the newest — stacks should get versions like packages do; the tank's
scores are the SDK's own until item 4 puts tasks in the runtime and the run's
outcome carries the score; and `deploy` needs a registry docker can push to,
which from a laptop means running the command on the box or a tunnel with
docker told about it — the box's registry is loopback by design.

---

## 2c. The dive goes through the scheduler

What the scheduler does today, read from the code rather than remembered: a
run is queued against a queue; an agent on a host claims the oldest queued run
it can serve and locks one whole GPU for it in the same statement; the
simulator gets that GPU; a controller that wants a GPU is put on the same one.
Devices are GPUs and nothing else — no processor, no memory, no GPU memory in
the decision. `gpuShare` is recorded and never used. A queue reports how many
devices are free; the client asks the first queue it was granted and the
Dive button knows nothing about what the dive will need.

That was right when every dive was one simulator and a person at the keys. It
is not right once a controller may be a model. A policy that needs ten
gigabytes of GPU memory beside a simulator that needs twenty does not fit on
a twenty-four gigabyte card, and today nothing would notice until the
container died.

**What a dive declares.** Its needs, assembled from its parts: the simulator's
— one GPU, its memory, the runtime; the controller's — GPU or not, how much
GPU memory, processors, memory, what it has to download; the mode — an
interactive dive needs a stream endpoint, a batch dive none. The controller's
needs come from its stack record, which the SDK writes when it deploys.

**What the platform does with them.**

- A device carries what it has — GPU memory, and the host's processors and
  memory — and what is already held on it. A run claims an allocation: one
  or more devices, each with an amount, locked together in one statement as
  the single device is now. The simulator and the controller may share one
  card when the memory allows, or take two; the scheduler decides, not the
  agent.
- Hosts report capacity every time they ask for work, as they report the
  runtime today.
- A request that cannot be placed anywhere is refused with the reason, as
  jobs are: no host has a card with that much memory, the queue is draining,
  the institution is at its quota. A request that can be placed but not now
  is queued with its position and what it is waiting for.
- Quotas per institution on concurrent dives and GPU-hours, as jobs have.

**What the Dive button does.** Assembles the needs from what is chosen — the
place, the vehicle, the controller, the task, the mode — asks the platform,
and shows what happened: placed on which host and which cards, or queued
behind what, or refused and why. The waiting screen shows the placement
progressing: allocated, images pulling, packages staging, simulator opening,
controller connected, running.

**Done when:** a dive with a GPU controller is placed only where the
simulator and the controller both fit, two such dives on the box are placed
on its two cards, a third is queued with its position shown, and a dive that
can fit nowhere is refused with the reason on the screen.

*Where it stands:* done, and verified on the box (3 September). Three dives
whose controller declares 10 GiB of a card were asked for in a row: the first
was placed on card 0 with the simulator's 20 GiB and the controller's 10
beside it, the second on card 1 the same way, and the third queued first in
line "waiting for a card with 20 GiB free for the simulator and 10 GiB for
the controller". A fourth whose controller declares 50 GiB was refused at
once: "this dive fits nowhere on that queue: this dive needs 50 GiB of one
card and the largest on this queue has 48.0 GiB", recorded in the refusal
ledger. The two placed dives ran side by side on DDS domains 1 and 2.

What changed. A dive's needs are assembled at admission from its parts — the
simulator's by mode (measured on the box: 20 GiB of card, 4 processors, 16
GiB for interactive; 16, 4, 12 for batch), the controller's from its stack's
declaration (`coral-city deploy --gpu-memory 8G --cpus 2 --memory 4G`), with
the request able to override — and copied onto the run. A run holds an
allocation, `dive.hold`, one row per part per card; a device may carry parts
of several runs when its memory allows, so the one-run-per-device index is
gone. The agent's claim locks its host's cards, walks the line oldest first
and places the first that fits: the simulator on the card with the most room,
the controller beside it when it fits, on another card when it does not. A
run carries its placement on every read — placed on which host and cards, or
its position and what it waits for. Refusals: fits nowhere, queue draining,
runtime not offered, institution at its limit of concurrent dives or of
GPU-hours in a day (both new quota fields), each with the reason in words.
Hosts report processors and memory with every claim. Each dive gets a slot on
its host, and its DDS domain and stream port come from that rather than from
the card, so two simulators sharing a card neither hear nor watch each other.
The agent runs dives side by side instead of one after another, which is what
had been leaving the second card idle, and its package cache serialises
assemblies of one version. The waiting screen shows the placement and the
steps — cards allocated, place staged, simulator opening, controller started,
stream open — and the Dive button shows a refusal's reason.

Follow-ups. The GPU memory the scheduler counts is what dives hold, not what
the card reports free; anything else on the card is invisible to it. The
simulator's needs are constants per mode until the runtime measures itself.
The job broker records its refusals inside the transaction it then rolls
back, the same flaw the dive path had; it should record them after. The
end-to-end script still registers devices the old way and has not been run
against the new claim. The waiting screen was typechecked and not watched.

---

## 3. The cockpit

The channel protocol, and what it makes possible.

- `hello`, `view`, `frame`, `pose`, `topic`, `event`, `control`, `objective`,
  `controller` — who is flying, and the parameters they expose
- Views: chase, free, top, front, vehicle camera, sonar — any as the large pane
- Minimap and top view drawn on the client from pose and the site outline
- The topic tree live on every dive, with rates and counts, and a visualiser per
  topic type
- The controller panel: which controller has the vehicle, its state, its
  tunables as controls, and a switch to any other the vehicle supports

**Done when:** four views can be open at once, the minimap shows the vehicle
moving over the site with its track behind it, and clicking `/depth` opens a
plot of it.

*Where it stands:* built, and the channel verified on a live Looe Key dive
(3 September); the screen itself typechecks and bundles but has not been
watched from the application, which needs a sign-in I do not do.

The console now has four panes in the middle, one large and three small, any
small one swapping into the large slot when clicked: the rendered water,
looked at through a camera chosen on the pane — chase behind the vehicle along
its own heading, front as its camera would see, top straight down with
heading up the screen, orbit circling it; the chart, drawn on the client from
a coarse height grid the dive hands over when a watcher arrives, with the
bottom shaded by depth, north up, a scale, where the dive began, the track
behind the vehicle and the vehicle pointing where it points; the section, the
last minute of depth with the bottom under the vehicle drawn in; and the plot
of whichever topic was clicked in the tree, every numeric field on it with its
latest value, fields toggled from the legend. The topic tree shows each
topic's rate and count; on a dive nobody's stack is listening to it shows the
vehicle's contract, and the plots still work because the runtime says what the
sensors would say on every state. The controller panel can hand the vehicle
to any controller — the hold, the assisted manual, or the ordinary rule of
the stack while it talks — and a hand on the keys still wins while it is
there. The vehicle panel gained heading, pitch and roll.

On the wire: a `hello` on connection (site, vehicle, views, where it began),
`view` and `engage` asks beside `held`, `tune` and `hold`, and on every
state `samples`, `view`, `pitchDeg`, `rollDeg`, and `rateHz` per topic. All
of it exercised from inside the simulator: hello carried a 64×64 map of the
reef 1000 m across from 0.86 to 34.1 m deep, the four views each took, engage
moved the vehicle between manual and the hold and the hold kept it after the
keys were released.

Follow-ups. The renderer draws one camera; a vehicle camera or a sonar as a
second rendered pane needs a second capture, and the chart, section and plot
stand in for them until then. The chart shows the site and the track but not
the coral or a task's waypoints — those come with item 4. A gamepad is not
read yet; keys only.

---

## 4. Tasks

Six, defined in the map, each with success criteria the platform evaluates as
the dive runs.

| task | what it asks | judged on |
| --- | --- | --- |
| **Hold station** | stay at a point and depth for a set time | radius held, depth band held, duration |
| **Waypoints** | visit points in order | each reached within a radius, in order, under a time |
| **Transect** | fly a line at a fixed altitude above the seabed | altitude band, heading tolerance, length covered |
| **Survey** | cover a rectangle in passes | fraction of the area seen, overlap, altitude |
| **Inspect** | approach a structure and circle it | object in frame, from how many bearings, at what distance |
| **Return** | come home and surface | distance from home, final depth, time taken |

Every one of them produces a result, not a pass mark: what was achieved, how
closely, how long it took, how much was asked of the thrusters.

**Done when:** a piloted dive shows its task and live progress, and a finished
dive has a result recorded against it.

*Where it stands:* done, and verified on the box (3 September). The dive page
sends the task's objective with the dive — the document the runtime judges,
measured from where the dive begins, so a task defined on the composer never
needs the site's coordinates. Five are judged: hold station (seconds on
station within a radius and a depth band), waypoints (reached in order within
a radius, half marks over the time limit), transect (metres flown within the
altitude band on heading), survey (fraction of the rectangle's half-metre
cells seen from within the altitude band with the swath), return (home and
surfaced). Inspect is listed and says why it cannot be chosen: nothing is
placed to circle. Every step the task keeps a score in [0, 1] and says how it
is going; the console shows it as a Task panel with a bar and a sentence, and
draws the task on the chart — the station's circle, the waypoints numbered
and filled as they are reached, the transect line, the survey rectangle. At
the end the result — score, seconds, what was achieved, mean thruster effort
— goes into the run's outcome, and the Dives page shows it on the row. A
batch dive now lasts as long as its task needs rather than ten seconds. The
SDK's tank scores with the runtime's own task code, so a controller scores
the same on a laptop and on the platform.

Verified: a batch hold-station dive under the runtime hold recorded its
result (2 cm off station, thruster effort 0.006); a hand-flown waypoints dive
showed the four points in the greeting and reached the first at 22 s with the
progress and score changing live.

Follow-ups. Survey coverage is geometric — a swath under the vehicle within
an altitude band — not what a camera saw; item 5 makes it the frames. Inspect
needs a structure in a place. A task's waypoints are relative to the start;
absolute points, and points picked on the chart, are for the composer later.

---

## 5. Data collection

A survey's product is the data. Frames, poses, and sensor output recorded to the
run's artefacts, with coverage computed from where the camera actually looked.

**Done when:** a survey dive leaves a recording that can be listed, fetched and
replayed, and its coverage is a number derived from the poses rather than an
assertion.

*Where it stands:* done, and verified on the box (3 September). A batch survey
dive under the runtime hold left a recording of 2,932 poses over its 600 s,
listed by the API with fetchable links and fetched whole by the SDK; its
coverage was 0 %, derived from the poses — it hovered 3.2 m up, outside the
altitude band, and never moved — which is the number a survey nobody flew
deserves. A batch hold-station dive left 323 poses and 60 frames over 65 s
with its result (score 1.0) in the manifest, and the frames show the vehicle
over the reef. A batch dive that records runs the renderer headless so its
frames exist, and the application now leaves when the dive is over, which is
how a rendered dive nobody watches hands its machine back.

A dive that is for something records as it runs, beside its brief: poses at
five hertz of simulated time — position, attitude, heading, depth, altitude,
velocity, which view was being looked through and which frame was last taken
— what every sensor said, how the task was going once a second, and the
frames at one hertz through the viewport's own capture. A survey looks down
by default, through a camera under the hull with the heading up the screen,
so what it records is what it sees; a console may look elsewhere and the pose
line says so. A manifest closes the recording with the counts, the camera as
the catalogue describes it, and the task's result. When the dive is over the
agent puts every file into storage the way every other file the platform
holds goes — declared by digest, checked, then named — and records each as an
artefact of the run; the run's outcome says how many. Whoever may read the
dive may list them, each with a link that fetches it, and the SDK fetches a
whole recording with `coral-city fetch`. The Dives page offers Replay on a
run that recorded: the frame nearest the moment beside the chart with the
track up to that moment, scrubbed or played.

Coverage is derived rather than asserted: a survey's footprint on the bottom
at each pose comes from the vehicle's camera — its field of view where the
catalogue states one, else its focal length read as a 36 mm equivalent — and
the altitude at that pose, and the cells that footprint covers are what count
as seen. The result says which it used.

Follow-ups. Frames are uploaded one file at a time, three requests each; a
long survey should bundle them. The recording is the rendered view, not a
sensor: a vehicle camera rendered on its own would record whatever the
console looks at with. The manifest now carries the site's coarse grid,
the coral and the task's geometry, so a replay's chart stands on the
recording alone; recordings made before that are charted about their start.

---

## 6. Fly all of it

Manual dive through the finished thing: start still, take the controls, run a
task, be scored, leave, and have the machine given back.

**Done when:** you do it and it is not annoying.

*Where it stands:* the journey has been driven end to end from a script on
the box, the way the application drives it, and what it found was fixed (3
September); the judgement — you, at the keys, not annoyed — is still yours to
make, and the numbers below say what to expect.

What the script does is what you will do: ask for a waypoints dive on Looe
Key in the BlueROV2, wait, arrive in the water, sit still for ten seconds
under the hold, take the controls and drive to the first waypoint, watch the
score change, let go and watch the hold take it back, surface, and look at
what is left. What it found: leaving a dive marked it cancelled and threw
away its result and recording, because the agent killed the simulator and
the record refused a finished run any further word. Now leaving a dive you
were flying ends it as succeeded and surfaced; the agent asks the simulator
to stop and the simulator closes the dive properly — flushes its recording,
says where the vehicle settled — and what it then reports is added to the
run rather than refused. The recording is written line by line and its
manifest rewritten as it goes, so even an unceremonious stop leaves it whole.
The Dives page shows a left dive as surfaced, its score, and Replay.

The scripted pass, as it stands: placed 3 s after asking; first frame 65 s
later; ten seconds still under the hold with a centimetre of depth drift and
no movement; the keys took the vehicle at once and the first waypoint was
reached in 14 s with the score at 0.25; letting go handed it back to the hold;
surfacing answered at once and, 45 s later, the run read succeeded and
surfaced with its Waypoints score, a recording of 101 files, both cards free
and no container left on the host. The whole thing, 161 s.

Follow-ups for the pass in the application: the first frame takes about a
minute after the dive is placed, all of it the scene opening; the waiting
screen says so step by step, but a minute is a minute. Keys are the only
controls; a gamepad would make it feel like a vehicle. The chart is drawn on
the client and does not yet show the coral.

---

## 7. The reef into the place

The place Isaac Sim opens still carries the grown reef. The surveyed colonies
become the place's coral layer, the grown one goes, and the dive begins on the
surveyed spur zone at working depth.

**Done when:** a dive opens in Looe Key on the surveyed reef, the frame from the
start point shows the spurs and the colonies the survey found there, and the
place's picture is that frame.

*Where it stands, 3 September:* done. `tools/reef-survey` wrote the 83,055
surveyed colonies as Looe Key version 6 with the start point on the spur zone
at 7 m; a dive opened there and photographed the vehicle among them. The
place's picture is the Blender dive-view frame, which is the better render;
Isaac's own frame still draws the old shapes and ground.

## 8. The application looks like the thing it is

The dive page, places and fleet as they are now are lists with "no picture
yet" on them. Every place and vehicle gets a real picture from its own
package; the dive page opens on the place you are about to dive; the
application carries its own icon and opens on its own image, not Electron's.

**Done when:** the dock shows the coral, the first thing on screen is the
Coral City image, and no card on the dive page says "no picture yet" for a
place that has been rendered.

*Where it stands:* the dive page is one composer over the place's picture,
with where, what in and for as three columns under it; pictures come from
packages, with a credit file beside a photograph; the boot screen carries the
image; the dock icon is set from the checkout. Looe Key carries its own render;
Kāneʻohe Bay, the Red Sea and the BlueROV2 carry licensed photographs from
Wikimedia Commons (CC BY 2.0, NASA public domain, CC BY-SA 4.0), credited on
their pages. The tow tank and the probe have none: a render of the tank from
inside is the remaining piece, and `tools/portrait.py` is the start of it.

## 9. Places connected to the sea

A place is somewhere real, so it says what the sea is doing there today.
Aqualink keeps a public record — satellite temperature, heat stress, alert
level, and where there is a buoy, live water temperature, wind and waves — and
Looe Key Reef has a buoy three hundred metres from our site centre. Each place
finds its nearest Aqualink site from its own extent and shows today's water.

**Done when:** the Looe Key card shows the buoy's current temperature and heat
stress, the place page shows the last weeks as a chart with the survey dives
that were logged there, and a place with no site nearby says so rather than
showing nothing.

*Where it stands:* done. Looe Key reads its buoy (31.3 °C, alert level 2 on
3 September), Kāneʻohe its nearest deployed site; the place page carries the
eight-week chart and the logged dives. Places founded without an extent take
their position from their package; the platform's extents are still zero and
should be set when a place is founded.

## 10. The environments we will build, said plainly

The places the platform is for — reefs surveyed at centimetres, an offshore
platform, a port, a wind farm, a wreck, a kelp forest — listed, disabled, with
what each takes to build and what it is for. So the shape of the product is
visible before the whole of it exists, and nobody mistakes an empty catalogue
for the product.

**Done when:** the places page shows them as unmistakably not-yet, each with a
sentence on what building it takes.

*Where it stands:* done, in `catalog/environments.ts`: eight, with standing and sources.

## 11. The fleet, understood

Every vehicle with a page that explains its physics: mass against buoyancy and
what that means for how it sits; added mass and damping per axis and the
terminal speeds they imply; every thruster drawn where it is and pointing where
it points, with the force each axis can muster. Numbers editable so a person can
see what a heavier battery or a bigger thruster does before anybody publishes a
version. The catalogue grows past the BlueROV2 with vehicles whose parameters
have a published source, marked as not yet flyable until they have a hull.

**Done when:** the BlueROV2 page shows the six thrusters drawn correctly, the
derived numbers match what the runner integrates, changing the mass moves the
net buoyancy live, and at least two more vehicles are catalogued with sources.

*Where it stands:* done. The page found something: the catalogue BlueROV2
displaces 0.011054 m³ and weighs 11.5 kg, so it sinks by 1.7 N — 170 g
negative — which is why every dive begins by falling and is the first thing
item 2 must fix. BlueROV2 Heavy (Wu 2018) and REMUS 100 (Prestero 2001) are
catalogued and marked not yet flyable. Publishing a version from the page is
not built.

## 12. Tasks on the dive page

The six tasks from item 4 chosen on the dive page before pressing Dive, each
with its success criteria shown, disabled until item 4 makes them real.

**Done when:** a task can be picked and the dive is defined with it, even while
the score is not yet computed.

*Where it stands:* done with item 4. The task is picked on the composer with
what it asks and what it is judged on, the dive is defined with its objective,
and Inspect is shown with why it cannot be chosen yet.

## Phase 2

Phase 1 is a platform that works: a real reef, a vehicle you fly, controllers
you write and deploy, dives placed by a scheduler, tasks scored, recordings
kept. Phase 2 makes it something people can rely on and something that
proves the point — a controller that learned, flying a task, scored. Same
rule as before: one item at a time, proposed, approved, built, checked off.

## 13. It does not fall over

The evening's flying found the ways it does: restarting the agent ended
every dive it was running; a dive asked for within twenty seconds of the
last failed on a port; the console sat on a dead dive. Some are fixed. The
rest of the class is: an agent that hands its running dives over to its
successor instead of killing them (reattach to the containers it left, or
drain before stopping); the job broker recording its refusals after the
rollback as dives do; autonomy stacks with versions in the API instead of
`slug-label`; the end-to-end script run against the new claim and kept
green; one state event a second thinned to one every five in the record; a
health page in the app that says what the box is doing.

**Done when:** the agent can be redeployed under a running dive and the
dive continues; the end-to-end script passes; the app shows the box's
health.

*Where it stands:* built and verified on the box (3 September). The agent
writes the handles a successor needs beside each dive's brief; when it is
stopped it hands its running dives over instead of ending them, and the
agent that starts next adopts them — renews their leases, relays what the
simulator says, waits for the end, keeps the recording, reports. Verified
by redeploying the agent under an interactive dive: the simulator stayed up,
the new agent logged the adoption, the run stayed running, and surfacing it
afterwards kept its recording. Also done: the job broker records its
refusals after the rollback; autonomy is builds under one name rather than
slug-label; the record takes a state every five seconds; the Profile page
shows the machines card by card with what each holds and what is in flight;
the end-to-end script, given a dive quota for its institution, passes 68 of
68 against the box.

Left open, and worth doing next: the box is shared, and with no dive running
card 0 carries thirty gigabytes of other people's work. The scheduler counts
only what dives hold, so it would happily place a twenty-gigabyte simulator
beside that. The agent should report each card's free memory when it asks for
work and the placement should trust the lesser of the two figures.

## 14. The application, tidied

Everything a person meets gets one pass with fresh eyes: the console's
panels laid out to one grid with nothing overlapping, the chart with the
coral and the task's points on it, a gamepad read beside the keys, the Dives
page as a real history — each run with its task, score, duration, controller
and a Replay that shows the site under the track — and the Autonomy page
real: the stacks the institution has, what each needs, which dives flew it,
and a way to deploy from the app.

**Done when:** you walk every page and nothing makes you swear.

*Where it stands:* in progress (3 September). Done so far: the console's
docks scroll and its controller panel has one shape; the section's labels
clear the pane name; a gamepad is read beside the keys — left stick surge
and sway, right stick yaw and heave, triggers roll — and sent as fractions
the vehicle adds to the keys; the dive page is a five-line plan — where,
in, flown by, water, for — each line the one chosen with a searchable list
behind it, so it holds five choices or five hundred at the same height
(chips wrapped and columns of cards did not scale); builds are folded into
controllers by slug on the dive page and the Autonomy page, newest chosen;
the Dives page is a table — name over who flew it and when, score, Replay,
state — rather than rows that wrapped;
Replay plays simulated time at 1× to 30×, draws the site, coral and task
under the track, and puts depth, altitude, speed and score traces under the
scrubber with the moment marked, each clickable to seek; the end-to-end
script sweeps what it founds (`./tools/box tidy`, also run on its own) so
test tanks and probes no longer pile up in Places; every picture went pure
white for a night (4 September) — the stream, the recordings, the
photographs — with physics, chart, task and instruments all fine and no
error anywhere. Found by running one brief by hand against the images still
on the box, halving what differed until one line remained: the coral chart's
read of the place, which decoded a 7.7 MB file and ran a regex over the
whole of it while the dive opened. Sleeping for the same tenth of a second
was harmless and a busy loop of the same cost reproduced the white, so what
the renderer cannot survive is the interpreter being held, not time passing.
The read now takes the bytes undecoded, parses only the two thousand
colonies a chart draws rather than eighty thousand, and lets go every so
often: 21 ms, and the same points. Tried and rejected: opening the dive a
few frames into the update loop instead — which put the picture out on its
own. Lesson kept: bisect with images, not with reasoning about what
"cannot" matter. The water got its two edges (4 September): the surface was
a picture with nothing behind it — the lid in the code only engaged for
places that ship a water layer, which Looe Key does not, and a dive that
afternoon reached 0.75 m above the sea and kept its buoyancy, its drag and
its thrust the whole way. Buoyancy, drag, thrust and added mass now follow
the share of the hull under the surface, so a vehicle driven up breaks the
surface, loses what was holding it up and falls back on its own; the lid is
gone. The seabed had a floor but no guard, so the helm gained one beside the
attitude guard: it takes the commanded descent away as the clearance runs
out, defends half a metre by default, never holds a vehicle back from
rising, and reports the clearance it is keeping. The ground became a surface rather than a
lift the same day: the floor clamped depth and killed the descent, which
carried a vehicle pressed onto a slope up it at no cost, so contact now
removes the part of the motion going into the surface — flat ground stops
the descent as before, a slope turns the push into travel along it and keeps
only what was not spent climbing, a face near vertical leaves almost
nothing — and a probe half its own width ahead stops it against ground too
steep to ride over before it reaches it. Worth knowing: Looe Key's height
field is 512 by 512 over a kilometre, so two metres to a cell, and its
steepest ground is 35 degrees. Real spur faces are steeper than that and the
grid cannot hold them, so how sharply a vehicle is stopped is set by the
survey's resolution and not by this code; the Autonomy page lists what is deployed with what each needs; the
Profile page shows the machines. Tried and parked: the BlueROV2 hull
decimated in Blender from 1.27 million faces to 60 thousand comes out at
8 MB and looks right in shape, but its 2,251 per-face materials render grey
after the round trip, so the 44 MB hull stays until the colours survive.
Still to do: the chart with the coral on it, and the walk through every
page.

## 15. Water that moves

Every dive so far is in still water. Constructed conditions gain a current
— speed, heading, a shear with depth — and visibility, both felt by the
physics and drawn by the renderer, chosen on the dive page and recorded on
the run. Observed conditions take the current from the place's Aqualink and
model data where there is any.

**Done when:** a dive in two knots of current needs a different controller
to hold station than one in still water, and you can see the difference.

*Where it stands:* built (3 September); the live check is below as it lands.
Constructed conditions carry a current — metres per second, the heading it
flows towards, the way a chart writes one — and a visibility. The physics
drags on motion through the water rather than over the ground, so a vehicle
doing nothing is carried and the hold spends thrust to stay: in the tank the
hold in 0.3 m/s keeps station with more than twice the thruster effort of
still water. The renderer scales its fog to the visibility asked for. The
dive page has a fifth column, "In water that is", with still water, a gentle
set, one knot, two knots, and one knot murky; the chart draws the current as
an arrow with its speed; the SDK's tank and `coral-city dive` take
`--current` and `--visibility`. Not yet: observed currents from the place's
data, a shear with depth, and the water drawn moving.

Verified live: a batch hold-station dive on Looe Key in one knot flowing east
with five metres of visibility. The hand-written hold could not keep it:
4.4 m off station, 4.8 of 60 seconds within half a metre, score 0.08 — a
knot is at the edge of what the BlueROV2's guarded surge can push against,
while in the tank it holds 0.3 m/s with room to spare. That is the point of
the item: a current that changes which controller is good enough. The
attitude guard is the lever a pilot has, and a controller that turned the
current onto the beam, where the hull has fifteen times the authority, would
be the clever one.

## 16. Sensors that are sensors

The vehicle's camera is published on `/camera/image_raw` as the contract
promises, rendered from the vehicle's own camera whatever the console looks
through, and shown as a pane; the recording's frames become the camera's;
the imaging sonar follows as a fan drawn from the seabed. A controller can
then be written against what the vehicle sees.

**Done when:** a stack subscribing to the camera receives frames, and the
console shows the camera and the chase view at once.

*Where it stands:* half (3 September). The vehicle publishes
`/camera/image_raw` as the contract promises — RGB frames at two a second —
whenever the picture being rendered is the vehicle's own camera, front or
down, which it is on every batch survey and whenever the console looks
through it — verified live: sixteen frames at two a second while the console
looked through the front camera, none once it went back to chase. A chase or
orbit picture is not published as a sensor. The other
half, the camera rendered on its own so the console can watch chase and
camera at once, needs a second render product, and the sonar with it.

## 17. The first policy

A controller that learned. Trained in the tank against a task with current
— station hold first, then waypoints — with the SDK's gym-style loop, on the
box's card as a batch job the scheduler places like a dive. Deployed with
`--gpu-memory`, flown on the platform, scored, compared with the hand-written
hold on the same dive and seed. The whole path a researcher would take, done
once by us so it is known to work.

**Done when:** a learned policy holds station in current with a score at
least as good as the hand-written hold's, from the console.

*Where it stands:* built, and the path walked once (3 September). The policy
is a linear map from what the vehicle sees — where it is relative to where it
began in its own frame, how deep relative to the start, how far its heading
has swung, its velocities — to the wrench it asks; its weights are found in
the tank by the cross-entropy method, seeded from the hand-written hold's
gains, against hold-station in a one-knot current: twenty-four candidates a
generation, fourteen generations, six minutes on a laptop. It is written out
as a controller with the weights baked in, `examples/learned_hold.py`, so the
file is the thing deployed. In the tank at a knot the hand-written hold scores
0.15 and the learned one 0.48 — it stays on station three times as long, at
twenty times the thruster effort, which is a policy that has learned to
fight and not yet to fight cheaply. Deep it is not: a network in place of the
matrix is the same path with more parameters, and that is the next thing to
try. What it proves is the path: tank, weights, deploy, fly, score.

Flown on the box in the same knot of current it trained for, it scored 0.03
— 7.8 m off station, worse than the hand-written hold's 0.08 in that water.
The tank had trained it on the true state with no delay between seeing and
acting; live it sees a dead-reckoned position with about a hundred and fifty
milliseconds between observation and thrust, and a high-gain policy that
thrashes is exactly what a delay undoes. The tank now takes `latency_ticks`
and the learner trains through the sensors with three ticks of delay and a
heavier price on thrust. Retrained that way it scores 1.00 in the tank at
the hand hold's thrust, and flown live in the same knot it scores 0.29 —
17.6 of 60 seconds on station, 1.9 m off at worst, against the hand-written
hold's 0.08 in that water. Better than the hand, as the item asked; a long
way from its tank score, which says the tank's picture of the live loop is
still too kind. The lesson is the one every sim-to-real paper reports, and
the platform now has the knobs to learn it with: what is still missing from
the tank is what the next run should measure.

## 18. Tasks you can lay out

Waypoints placed by clicking on the chart, a transect drawn as a line, a
survey as a rectangle, saved with the dive; results across the runs of one
dive shown together, so a change to a controller is a change in a number.

**Done when:** you draw a survey on the chart, fly it twice with two
controllers, and see which did better.

*Where it stands:* the second half first (3 September). The Dives page shows
each dive's scored runs side by side — score bar, who flew it, seed, thruster
effort — so two controllers on one dive are two lines to compare. Laying a
task out on the chart is still to do.

## 19. Run it again

A run pins everything it needed. Ask for it again with the same seed and
compare the trajectories; a difference is a bug in the platform's own claim.
Then the same dive across many conditions at once, which is the scored batch
the roadmap always wanted.

**Done when:** two runs of one seed leave the same trajectory, and a
difference between controllers is shown as a difference between tracks.

*Where it stands:* the command line has it (3 September): `coral-city dive
--seed N`, `coral-city dive --again <dive>/<run>` to run one exactly again,
and `coral-city compare <dive> <runA> <runB>` to hold two recordings' poses
against each other and report the largest difference in position. Verified
on the box: a hold-station dive in a gentle current, seed 42, run twice —
323 poses each, the largest difference in position 0.0000 m, identical to the
millimetre. The claim the platform rests on holds. Still to do: the same dive
across many conditions at once, and two controllers' tracks drawn together.

## Phase 3 — a dive that is for something

Phase 2 made the console honest and the water real. What it did not do is make
a dive *mean* something: a task is measured but nothing flies it, a dive ends
when its clock runs out rather than when its job is done, and a vehicle has
neither a reason to come home nor anything to come home to. This phase is
about the mission.

One thing has to be said first, because it shapes the order. A waypoints dive
run today sits exactly where it started and scores zero — the task watches, and
the hold holds. Every task below is worthless until something can fly one, so
that comes before the tasks themselves.


## 20. Put the vehicle where you want it

Flying a kilometre across a reef at a quarter of a metre a second to reach the
thing you want to look at is forty minutes of nothing. On a manual dive,
clicking the chart should put the vehicle there: placed, stopped, with the hold
taking the new pose, and the depth taken from the bottom at that point unless
you say otherwise.

It is a hand of God and the record has to say so. A dive that was picked up and
moved is not a dive a controller flew, so the run carries how many times it
happened and its task score is marked as handled — otherwise the Dives page
would compare a controller that did the work with one that was carried.

**Done when:** you can click anywhere on the chart, arrive there, and the run
says plainly that you did.

*Where it stands:* done and verified on the box (4 September). Double-clicking
the chart carries the vehicle: on a live dive at Looe Key it went from
(115.2, −25.0) to exactly the point asked for, at 2 m over the bottom there
rather than the depth it had been at, stopped, with the hold taking the new
pose and the route re-steered from where it now is. The count is in the state,
the recording and the result, and a carried run is left out of a trial's
arithmetic and said so.


## 21. Something in the platform that can fly a task

Between the hold, which stays where it is put, and a stack somebody wrote,
there is nothing. So the platform gets a guidance controller of its own: line
of sight to the next point, depth held on the way, arrival by radius, and the
same tuning knobs on the console as everything else. It is not clever and it
is not meant to be — it is the reference every written controller is measured
against, and the thing that makes a task on the dive page mean what it says.

**Done when:** choosing Waypoints and pressing Dive flies the waypoints.

*Where it stands:* done (4 September). `coral/controllers/pursue.py`: turn
towards the point, run at a speed that eases off as it arrives, hold the depth
or the altitude the leg asks for, hold at the end. A leg can also say how close
counts as arrived, how slowly to come in, what to keep facing, and how long to
stay — which is what docking to forty centimetres and holding ten seconds over
a colony to sample turned out to need. Flying the tasks found both gaps: an
inspection that looked where it was going saw one side of twelve, and a revisit
that did not stay sampled two marks of three.


## 22. A dive that ends when its task does

A task reports done; the dive ignores it and runs to its clock. Reaching the
last waypoint should end the dive, and so should failing: running out of time,
running out of battery, or being told to surface. The run's outcome says which
of those it was, the console says it in words, and a batch dive hands its
machine back the moment there is nothing left to do.

**Done when:** a waypoints dive asked for an hour ends in four minutes,
succeeded, because it finished.

*Where it stands:* done and verified (4 September). A reach asked for 400 s
ended at 88.3 s, `achieved`. Every ending is named: achieved, failed, battery,
surfaced, home, or time.


## 23. Energy: a battery that runs down, and runs out

Nothing in the vehicle costs anything, so nothing has to be decided. A battery
changes that: capacity and hotel load declared by the vehicle package the same
way its mass is, power drawn from what the thrusters are actually doing, state
of charge on the console, on the `/battery` topic a stack can subscribe to, and
in every recording. Flat means flat — the thrusters stop and the hull does
whatever its buoyancy says. Every task result carries the energy it spent
beside its score, because a controller that does the job on half the charge is
the better controller and today there is no way to say so.

The numbers come from the vehicle package, not from here: the BlueROV2's
stock pack and its thruster curves are published, and inventing them would
make every energy score a fiction.

**Done when:** two controllers fly the same task and the record shows which one
was cheaper.

*Where it stands:* done and verified (4 September). The BlueROV2 package now
declares its pack and its thrusters' power, published as version 4. A 25 m
transit costs 0.74 Wh at 27.8 W; treating 193 colonies over 135 m costs 4.7 Wh.
It is on the console with its reserve marked, on `/battery`, in the recording
and beside every score. Flat stops the thrusters and ends the dive.


## 24. The failsafe that decides to come home

With energy there is something to run out of, and with a dock there is
somewhere to go. The failsafe sits above every controller in the helm — above
even a hand on the keys — and holds one decision: whether what is left in the
battery still covers the journey home with a margin. When it stops covering
it, the vehicle goes: to the dock if the dock is reachable, to the surface if
it is not, and it says which it chose and why. A vehicle that dies on the
bottom because nobody was counting is the failure this exists to prevent.

**Done when:** a dive run with a battery too small to finish surfaces on its
own, and the record says it decided to.

*Where it stands:* done and verified on the box (4 September). Sent 300 m with
11.5% of a charge, it flew 127 m, decided at the reserve and surfaced on its
own — ended `surfaced` at 0.13 m with 10.0% left. It outranks a hand on the
keys, and a hand on the keys is the one thing that takes the vehicle back.


## 25. Things in the water

A place is a bottom and its coral. Tasks need more: a target to find, an
instrument to inspect, a dock to return to — objects planted at known
positions, drawn in the scene, and known to the runtime as truth to score
against. This is the layer under items 26 and 27 and it belongs in the place
package, versioned with everything else, so a dive that found something can be
run again and find the same thing.

**Done when:** a place can carry objects, and a dive can be scored on what it
did about one.

*Where it stands:* done as far as the tasks need it (4 September). A thing is
named either in the place's own coordinates or as so far ahead and to starboard
of where the dive began, and the tasks score against it: the search's target,
the inspection's structure, the revisit's marks, the dock's station. The coral
is the real thing already — the treatment reads the colonies the survey found,
unthinned.


## 26. The tasks worth flying

With something to fly them and something to fly them at:

  - **Reach a point.** The one everything else is built on: get there, and be
    judged on how far you travelled against how far it was, how long it took
    and what it cost. The interesting part is the bottom — the short way over
    a spur is not the short way through the water.
  - **Find something.** An object is planted where the vehicle is not told;
    the vehicle searches, and reports where it thinks the thing is. Scored on
    whether it was right, how close, and how long it took. This is the first
    task that needs the camera to matter.
  - **Treat an area.** A patch of real coral, and the vehicle has to pass
    within reach of every colony in it, low enough and slow enough to do
    something about them. Scored on the share of colonies covered and the
    ground it went over twice. We have eighty-three thousand real colonies to
    score against, which is what makes this worth doing here.
  - **Inspect.** Hold a thing in frame from a fixed distance while going
    around it. Scored on how much of it was seen and how steady the camera was.
  - **Revisit.** Go to each of a list of marked colonies, hold there long
    enough to sample, and come back. It is the survey a reef monitoring
    programme actually runs.

**Done when:** each one can be chosen on the dive page, flown by the platform's
own guidance, and scored the same way twice.

*Where it stands:* done and every one flown on Looe Key (4 September):
reach 25 m — score 1.00, directness 1.00, 88 s, 0.74 Wh;
find it — found at 355 s, score 0.83, closest pass 5.3 m;
treat a patch — 193 of 193 colonies, score 1.00, 135.6 m, 4.7 Wh;
inspect — 12 of 12 sides, score 1.00, 173 s;
revisit and sample — 3 of 3, score 1.00, 159 s;
dock — docked at 0.40 m and 0.015 m/s, score 1.00, 122 s.


## 27. Docking, and a dive made of stages

A dock is a place to charge and to hand over what was recorded. Docking is the
hardest thing here and the most real: an approach cone, a tolerance on position
and attitude, a speed slow enough not to break anything, and a positive
latch — or a miss, which is a result too.

It also forces the structural change this phase has been heading towards: a
dive stops being one objective and becomes a sequence. Fly a survey, dock,
charge for five minutes, undock, fly another. Each stage is scored on its own
and the dive is scored on all of them, and a stage that fails ends the mission
with the reason.

**Done when:** one dive surveys, docks, charges, undocks and surveys again,
and the record reads as five things that happened rather than one.

*Where it stands:* done and flown (4 September). Survey, dock, charge for five
minutes, survey again: four stages in order, each scored on its own line,
mission score 1.00, ended `achieved` at 732 s. A stage that fails ends the
mission and the record says which one. The battery fills while it sits on the
station.


## 28. Trials, not runs

One run of one seed is an anecdote. A trial is the same dive over a set of
seeds and conditions, run without anybody watching, reported as a mean and a
spread. It is the only honest way to say one controller is better than
another, and it is what makes the learning in item 17 worth continuing.

**Done when:** the Dives page can say a controller scores 0.82 give or take
0.05 over twenty runs, and show the worst one.

*Where it stands:* done in the application (4 September). Runs are grouped by
the dive and who flew it, and reported as a mean, a spread, the worst and the
best, with every run's score as a tick on the band and the average energy
underneath. Runs that were carried by hand are left out and said so.


## 29. Things going wrong on purpose

A controller that has only ever flown a healthy vehicle in still water has not
been tested. A dive should be able to lose a thruster at a stated time, have
its sensors go quiet for a few seconds, or take a gust of current — declared
in the conditions, recorded with the run, and identical on a re-run.

**Done when:** a dive can be defined with a thruster that fails at two minutes,
and two runs of it agree.

*Where it stands:* done (4 September). The conditions carry failures: a
thruster dead at a stated second, sensors quiet for a stated span — quiet, not
zero, because a controller that reads missing as zero is the bug this finds —
and a gust of current. Two runs of one failure agree to the millimetre.


## 30. Batch dives at the speed of the machine

A batch dive with nobody watching still runs at wall-clock speed, sleeping
between steps to keep pace with a clock nobody is reading. An hour of dive is
an hour of GPU. Unpin it from the wall clock when nothing is being rendered or
streamed and a trial of twenty runs stops being a day's work.

**Done when:** a sixty-second batch dive takes a fraction of sixty seconds, and
lands in exactly the same place as one that took sixty.

*Where it stands:* done (4 September). A batch dive with no watcher, no stack
and no hand on it runs as fast as the machine will carry it, in bites that stop
at the next frame its recording is owed. The four-stage mission simulated 732 s
in 203 s of wall clock; the treatment 574 s in 161 s. The step is the same fixed
step, so the trajectory is the same either way.


# Phase 4 — the vehicle is asked, not driven

Two hundred and seventy-five dives said almost nothing, and the reason is
structural rather than a matter of scale. Every task carries a `route()` that
is the answer to itself: the survey hands over its own lawnmower, the treatment
hands over its colonies in order, and the platform's guidance follows the line
it was given. The question and the answer come out of the same object, so no
controller is being measured, and the technology a vehicle navigates by barely
shows because there is nothing to get wrong over thirty metres.

What real vehicles do is not the problem. A HUGIN flying a preplanned lawnmower
on INS and DVL is exactly this, and it is most of the industry. The problem is
that we score the plan we supplied, over distances too short for error to
compound, and call the result a comparison.

Fixing it in this order, because each step is worthless without the one before.

---

## 31. A task states its goal, not its solution

`route()` comes out of the scored path. A task says what it wants — a place to
be, an area to cover, colonies to treat, a dock to sit in — and what counts as
having done it. Nothing about how.

What flies it becomes an ordinary controller like any other: `plan.py`, the
baseline, which reads the goal and works out its own route by the same
arithmetic the tasks used to hold. It is deployed and pinned the way a written
controller is, and it appears in results under its own name. Anybody's
controller starts level with it.

**Done when:** no task class can name a waypoint, every dive on the record says
which controller flew it, and the baseline scores what the built-in guidance
scored before — because the route is the same route, moved to where it belongs.

---

## 32. Missions long enough for navigation to matter

Ten metres cannot tell dead reckoning from an LBL array, and the matrix proved
it: still water, five technologies, one number. Real missions are kilometres
and tens of minutes, and that is the whole reason navigation error is a
subject — it compounds.

Task parameters move up an order of magnitude: transects of hundreds of metres,
surveys of hectares, transits with a return leg. Dives run free at the machine's
speed, as the batch already does.

**Done when:** the same task, flown on dead reckoning and inside an array, gives
two clearly different results, and the difference is drift rather than luck.

---

## 33. A task says what it needs to know

Positioning and tasks are not independent, and pretending they are is what made
the matrix flat. Docking needs a bearing to the dock, not a position in the
world. A georeferenced mosaic needs absolute fixes or the product is wrong even
when the flying was right. Close inspection needs nothing absolute at all.

Each task declares the kind of position knowledge it requires — absolute,
relative to a named thing, terrain-relative, or none — and the platform refuses
a dive it cannot support, saying why, instead of flying it and scoring nothing.

**Done when:** the composer greys out what cannot work, with a sentence about
why, and the matrix has feasible and infeasible regions rather than a wash.

---

## 34. A controller with two clocks

An inner loop at the physics rate that must be quick and must not fail, and a
deliberative loop at a fraction of a hertz that may be slow, may reach the
network, may call a model, and may return nothing. The inner loop keeps flying
whatever the outer one does — holds its last plan, and the failsafe still
outranks both.

Without this split there is no way to write a controller that thinks. With it,
a vision-language model looking at a frame every two seconds is an ordinary
citizen of the platform.

**Done when:** a controller can take two seconds to answer and the vehicle
neither stops nor lurches, and a controller that throws in its slow loop is
recorded as having done so and keeps flying.

---

## 35. A plan is a document, in a format that exists

Borrowed rather than invented: the shape of an IMC plan — a graph of manoeuvres
with parameters and transitions — which is what Neptus speaks and what the
LSTS toolchain has flown for years, with an eye on MAVLink's mission items,
which our own BlueROV2 already understands.

Then a plan is a thing that can be written by a person, emitted by a model,
diffed, stored with the run, and replayed. What the vehicle is given is the
same artefact whoever wrote it.

**Done when:** a dive can be flown from a plan document alone, the document is
kept with the run, and two plans for the same task can be compared side by side.

---

## 36. Tasking in words, at the dock

The language layer, last, because it is worthless before the rest and easy
after it. A task given as text — or a photograph of a reef with a circle drawn
on it — is turned into a plan document by a model, shown to a person, and
flown.

It happens at the dock or the surface, over a real link, because the acoustic
channel is JANUS-shaped: a few hundred bits a second, seconds of latency,
lossy. Sending prose down it is not physics. What goes down is the compiled
plan, or a short code that selects one.

**Done when:** somebody types what they want, sees the plan it became, changes
one thing about it, and flies it.

---

## 37. The benchmark, and the leaderboard

The point of all of the above. Fixed seeds, identical water, identical fit,
budgets for time, energy and tokens; every controller build flown over the same
task set; results kept as a table that grows: score, drift, energy, time,
and what it cost to think — tokens and latency — because a controller that
scores five per cent better and costs a second a step is not obviously better.

**Done when:** two controllers can be compared on one screen over the same
hundred dives, and the difference between them is attributable to something.



# Phase 5 — the Red Sea, and a vehicle that has no thrusters

Everything above was built against one reef in Florida and one small ROV on a
tether, and both of those choices are now load-bearing in ways nobody chose.
The water has a density constant in it. The vehicle has six thrusters and a
wrench, and every layer between a controller and the water assumes force.

The work KAUST is doing is the reason to fix it: a hundred hectares at Shushah
Island divided into operational grids, two million corals outplanted by 2030,
monitored by AUVs and photogrammetry. Their water is the saltiest open sea on
earth. Their vehicles include a Seaglider, which does not have a propeller.

A Seaglider is also the vehicle that most exercises what this platform is for.
It carries no Doppler log — too hungry for a ten-month mission — and hears no
acoustic fix underwater. It dead reckons by running its own hydrodynamic model
as a velocity sensor and does not see GPS again until it surfaces, hours later.
The standard scientific product of a glider dive is the depth-averaged current,
worked out from the gap between where it reckoned it would surface and where
GPS says it did. That gap is the thing every other dive in this list treats as
an error, and a glider hands it over as the result.

---

## 38. Water that has a density

Salinity and temperature belong to the conditions, next to the current and the
visibility, and density follows from them. At present `DENSITY_SEAWATER` is
1025 and it is an argument to the vehicle's constructor, which puts the
water's own property inside the vehicle — so a dive cannot ask for different
water, and two dives in different seas are the same dive.

Compare the two sites rather than a site against a constant. Looe Key in
summer is 36 PSU at 29 °C, which the UNESCO equation of state makes 1022.8;
the northern Red Sea is 40.6 PSU at 26 °C, which is 1027.3. On our BlueROV2
that moves net buoyancy from −1.90 N to −1.42 N — a quarter of the vehicle's
entire trim, and the depth loop's feed-forward with it. On a Seaglider it is
more interesting still: a hull ballasted for ordinary seawater is 127 g buoyant
in the Red Sea, and cancelling that costs 124 cc — a third of the working range
of a buoyancy engine that is the vehicle's only means of propulsion.

There is a second effect worth having. A depth gauge is a pressure sensor and a
division, and the number it divides by is a density chosen on shore: one set
for 1025 and flown in the Red Sea reads 100.22 m at a hundred. Small, but it is
a bias rather than noise — the same fraction wrong at every depth, and worse
the deeper the vehicle goes — which is the opposite of how every other error in
this platform behaves, and today it cannot be simulated at all.

**Done when:** a dive states the water it is in, the same vehicle floats
differently in the Red Sea than in Florida, and a depth sensor trimmed for the
wrong sea is wrong by the right amount.

---


*Where it stands:* done (13 September). Salinity and temperature are
conditions, density follows through the UNESCO equation of state verified
against its published check values, and `densityKgM3` overrides both for water
somebody measured. Looe Key is 1022.8 and the northern Red Sea 1027.3, which
moves the BlueROV2's trim by a quarter. A depth gauge states what it was
calibrated for and reads a fixed fraction wrong when that is not this sea.
Water that says nothing keeps the old constant, so nothing already in the
record moved.

## 39. A hull that is squeezed and chilled

Volume is a constant in the package, and for a vehicle that works at five
metres that is fine. For one that works at a thousand it is not: the hull
compresses with pressure and shrinks when cold, and on a glider the volume
that change accounts for is comparable to the whole authority of the buoyancy
engine. Eriksen's flight model does not write V, it writes V(t, p, T), and the
reason is that on this vehicle the difference flies it.

**Done when:** a vehicle package states its compressibility and thermal
expansion, and a dive to depth has to trim for the hull it will have down
there rather than the one it had at the surface.

---


*Where it stands:* done (13 September). The equation of state gained its
high-pressure term, verified against the published values at a thousand bar:
water at a thousand metres is 0.415% denser, four kilos a cubic metre, as much
as the whole gap between the two sites. A package may state a compressibility
and a thermal expansion, and whether a hull grows heavier or lighter as it
descends is which of those two wins — which is tested, because it is the design
problem of a glider rather than something a simulator may assume. Conditions
carry a temperature profile down the column. No catalogued vehicle states the
coefficients yet: the BlueROV2 works in a hundred metres where the effect is
small, and inventing a number for it would be the same fault as the thruster
position this phase began by fixing.

## 40. Propulsion that is not thrust

A controller answers with a wrench, or with thruster commands, and the helm,
the attitude guard, the allocator and the failsafe all assume one of those two
is what a vehicle takes. A buoyancy glider takes neither. It is told how much
to displace and where to put its mass, and its wings do the rest.

So a third form: a vehicle package declares what it is commanded in, and a
controller answers in the vehicle's own terms. The attitude guard becomes the
vehicle's rather than the platform's along the way, because a guard that holds
lean below thirty degrees is protecting an ROV from turning over and is
strangling a glider whose entire method is to fly at a steep angle.

**Done when:** two vehicles that are commanded in different units are flown by
the same helm, and neither knows about the other's actuators.

---


*Where it stands:* done (13 September). `Command` gained a third form and a
package says what it is commanded in. The assumption turned out to be buried a
layer below where anybody was looking: the allocator refused a thrusterless
hull outright, with the message "a vehicle with no thrusters cannot be flown" —
the platform's belief about what a vehicle is, written down. The attitude guard
is the vehicle's now rather than the platform's.

## 41. The Seaglider

The AUV of AUVs: 1.8 m, 52 kg, a thousand metres, a quarter of a metre a
second, ten months in the water, and no propeller anywhere on it. It moves by
displacing about 800 cc more or less than its own mass of seawater and letting
a pair of wings turn falling into going somewhere, and it steers by rolling a
mass inside itself.

The flight model is Eriksen's and it is taken from the paper rather than
invented: lift and drag parameterised on angle of attack and dynamic pressure,
pitch as the sum of attack angle and glide angle, glide slopes from 0.2 to 3.
Buoyancy from the difference between the vehicle's mass and the seawater its
volume displaces, which is why 38 and 39 come first.

What it cannot do is as much of the point as what it can. It cannot hover: a
glider that stops flying falls. It cannot hold station, which is the first task
this platform ever had. It cannot make headway against much more than 0.4 m/s,
so three of the five waters in the matrix simply carry it away — and that is
the envelope, not a defect to tune out.

**Done when:** a Seaglider flies a sawtooth to depth and back on buoyancy
alone, and refuses a task that asks it to hover instead of quietly failing at
one.

---


*Where it stands:* done (13 September) and flown. Eriksen's flight model
from the paper, a pump with a rate, a battery on a screw thread. It glides at
0.09 to 0.28 m/s on slopes of 2.1 to 3.5. A real dive in the Red Sea: an hour,
2,131 m travelled, climbed from 520 m to 52 m, **zero thrust**, half a
watt-hour, an endurance of 833 days. What the wings buy turned out not to be
the forward motion — a slender hull slides like a sled whatever you do — but
the exchange rate: more distance per metre of depth, at a lower speed.

## 42. Missions a glider can be given

`hold-station` is impossible, `waypoints` is the wrong shape, and a survey
flown as a lawnmower at constant altitude is a thing this vehicle cannot do.
What it does instead is a **section** — a sawtooth along a line, sampling the
water column as it goes; a **profile** — down to a depth and back, the unit a
glider mission is actually built from; and a **virtual mooring** — holding a
place by circling it, which is the closest a vehicle that cannot stop gets to
staying put.

**Done when:** a glider mission is stated in the terms a glider pilot uses, and
the tasks an ROV flies and the tasks a glider flies live in the same list
without either pretending to be the other.

---


*Where it stands:* done (13 September). `profile` and `section`, and a
refusal: a task declares whether it needs the vehicle to stop, a vehicle
declares whether it can, and a glider asked to hold station is told before the
dive rather than falling out of the water column while the clock runs. Flying a
real one found the other half of it — the platform put the glider on the seabed
of a six-hundred-metre site and then asked it to profile the top three hundred,
because the default start is the middle of the water and that is right only for
something that can stop there.

## 43. Navigation by flight model, and the current as the answer

A new way of knowing where you are, and the one this platform has been building
towards without having an example of it. No Doppler log, no acoustic fix, no
aiding of any kind between one surfacing and the next: the vehicle estimates
its own speed through the water from the model it flies by, integrates that for
hours, and finds out how wrong it was when GPS comes back.

Then the difference between the reckoned surfacing position and the true one is
divided by the time down, and that is the depth-averaged current — the thing a
glider is sent out to measure. Every other row in the positioning table treats
that difference as the error being studied. This one sells it.

**Done when:** a glider surfaces, the gap between belief and truth is reported
as a current, and the number is close to the current the dive was actually
given.

---


*Where it stands:* done (13 September). The physics gap closed with it: a
vehicle without bottom lock now dead reckons on its speed *through the water*,
so the current accumulates invisibly, which is the error no instrument fixes.
On surfacing the gap between the reckoned position and the satellite fix,
divided by the time down, is reported as the depth-averaged current. The real
dive drifted 907 m in an hour and that number is the measurement.

## 44. Long missions, cheaply

A glider dive cycle is hours and its endurance is months, against the twenty
minutes every dive in this record has taken. The saving grace is that a glider
is a water-column vehicle and not an imaging one: nothing about a section needs
a camera, so nothing about it needs Isaac. Flown as physics alone, at a step
chosen for the vehicle rather than for a renderer, a dive that takes six hours
of simulated time need not take six hours of anybody's afternoon.

**Done when:** a multi-day glider mission runs without a GPU, and a dive that
does need pictures still gets them.

---


## 45. A reef somebody surveyed

Their site, from a survey. The Red Sea Decade Expedition published the
OceanXplorer multibeam as GeoTIFFs on Zenodo — 2,863 lines over 49,418 km², one
grid at 40 m over the deep survey and six at 5 m in the shallows — and the
Allen Coral Atlas has benthic and geomorphic classes at 5 m over every reef
shallower than fifteen metres. Between them that is bathymetry and habitat from
the same kind of measured source Looe Key was built from, which is the standard
this platform already holds itself to.

*Where it stands:* half done, and deliberately not the site this item named
(13 September). Zenodo returned 504 from every route for the whole day, so the
multibeam was unreachable and the Allen Coral Atlas wants an account. What was
reachable was Sentinel-2 — ten metres, every reef on earth every five days, no
account — and in water this clear the bottom is plainly in the picture. So
**Al Fahal off Thuwal** is built and published instead: three kilometres square
at 5.9 m samples from one scene with 0.00% cloud, shape from Stumpf's log-ratio,
coral placed from the imagery rather than scattered, and both KAUST tasks flown
over it at a hundred per cent. It is honest about itself — `surveyed: false`,
with the method named — and `tools/get-reef` will do the same for any reef
anywhere.

What is still owed, in order of what it buys:

  **Calibrated depths.** Stumpf gives shape, not metres; the scale is currently
  set against the reef's own geomorphology. ICESat-2's ATL24 is NASA's laser
  measuring real depths along track, **fifty-seven granules cross this reef**,
  and two of them would pin the constants properly. It needs a free Earthdata
  account, which is a person's to create and not this platform's.

  **Shushah itself,** when Zenodo is up or when there is a reason to ask KAUST
  for their own survey of their own reef — which is the better demonstration
  and the better conversation.

  **Resolution that matches the work.** See 58: 5.9 m samples under a task that
  scores to 0.6 m is the mismatch that matters most here.

## 46. A picture you could reconstruct from

Coverage is scored as area passed over, and that is not what a photogrammetric
survey is for: a run that covers every square metre at the wrong altitude, or
in a roll, or too fast for the shutter, produces images nothing can be built
from and scores full marks. Overlap between frames, altitude held steady enough
for scale, and motion slow enough to be sharp are what make a reconstruction
possible.

**Done when:** two surveys that cover the same ground score differently because
one of them could be turned into a model and the other could not.

---


*Where it stands:* half done (13 September). The `monitor` task scores a grid
cell on coverage that is *usable* — imaged from inside a tight altitude band
and slowly enough not to smear — and reports separately how many steps were too
high and how many too fast, so a cell that came back at forty per cent says
which problem it had. What is missing is overlap between frames, which is the
third thing a reconstruction needs and the only one of the three that is about
the relationship between two photographs rather than about one.

## 47. Tasks a reef programme actually sets

The eleven tasks in the matrix are manoeuvres with a score attached — reach a
point, cover a rectangle, hold a station. They are the right tasks for asking
whether a controller can fly, and they are nobody's job. No reef programme has
ever funded a dive to hold station for five minutes.

What KAUST is actually doing at Shushah Island is a hundred hectares cut into
operational grids, two million corals outplanted by 2030, in-situ nurseries
making a hundred thousand a year, and the whole of it monitored by vehicles
carrying cameras. So: **monitor a grid cell** to a standard a reconstruction
can be built from, and come back with what is on it; **outplant** — visit a
set of planting positions, place something at each, and log where it went;
**census** — find the colonies in an area and say which are bleached; **tend a
nursery** — visit every structure and image it.

These are not harder than what is already here. They are the same geometry
with the work put back in, and the difference is that somebody would pay for
the answer. It also gives the model-driven controller and the model-driven
planner something worth being asked, which neither has had.

**Done when:** a dive can be given a job from the restoration's own vocabulary,
and what it comes back with is a finding rather than a score.

---


*Where it stands:* two of the four, done and flown over a real reef
(13 September). **`outplant`** — visit the planting positions of a cell, place
a coral at each, and be scored on how many went where they were meant to rather
than how many went in. A drifting vehicle plants every one of them, logs
thirty-five of thirty-five, and gets none of them on the mark; that gap is the
whole task. **`monitor`** — a cell covered to a standard something can be
reconstructed from, with the colonies it imaged reported as the finding. Both
scored 100% on Al Fahal with an array overhead.

Still owed: **census**, which needs the coral to have a condition — colonies
are geometry and colour with no health state, so "report the bleached ones",
the actual reason anybody sends a vehicle, cannot be posed. And **nursery
tending**, which wants the structures of 52 to exist first.

## 48. A dive flown from words, end to end

Drafting exists: the control plane asks a model for a plan document, checks it
against the vehicle's envelope, and refuses what the hull cannot do. It has
never flown. Nothing connects the plan a model wrote to a dive that runs, so
the language layer is a demonstration of itself.

Close it. Somebody types what they want, sees the plan it became, changes one
thing about it, presses Dive, and watches the vehicle fly the document that
came back. The same artefact all the way down — written by a model, read by a
person, flown by a controller, kept with the run and replayable afterwards.

**Done when:** a dive in the record has a plan nobody wrote by hand, and the
words that produced it are stored beside it.

---


## 49. A controller that is a model

`ponder` is the shape of a model-driven controller with the model left out:
the fast loop flies whatever plan it holds, the slow loop thinks on its own
clock and is charged in simulated seconds, a decision that fails leaves the
last one flying. All of it built and tested around a `_decide` that returns
the same route the platform's planner would.

Put something in it. A model that is handed the goal, what the vehicle
believes about itself, and — this is the part worth building for — what the
camera is looking at, and that answers with a plan it has changed its mind
about. A survey that sees bleaching and stops to look. A transect that finds
the reef is not where the chart said.

Then the benchmark has two contestants and item 37 finally means something:
two controllers over the same hundred dives, and the difference attributable
to something. Every dive in this record so far was flown by the same
arrangement of PID loops.

**Done when:** a model flies a dive it was not given a route for, and the
record says what it decided, when, what it cost in tokens and seconds, and
whether it did better than the loops.


*Where it stands:* built, wired, and never once run (13 September). The
`asking` controller is tested for the arrangement rather than for the model,
which is the part that has to be right before anybody spends a token: prose is
refused, a plan beyond the vehicle's envelope is refused with its reasons, an
unreachable model leaves the last good plan flying, and the tokens and seconds
land in the result beside the score. A dive may name it with `flyWith`, and the
worker grants a network and passes the key to those dives and no others —
everything an institution submits still runs with no route off its own network.

It has not talked to a model. The agent could not be redeployed while a sweep
was in the water, and until it does this is an assertion rather than a result.

## 50. Both cities look wrong

*Not the same as 45.* That one is whether the ground is real. This is whether
it looks like anything. Al Fahal's shape is now defensible and its surface is
not, and the two are fixed by different work.

Open. Al Fahal and Thuwal Deep are both built, both published, both flown, and
neither is fit to put in front of anybody.

The reef renders as pale colonies floating over a dark floor. The cause is
known and specific: the seabed is surfaced with a satellite photograph, and a
satellite photograph has already been down through fifteen metres of water and
back. Handed to a renderer as an albedo it gets attenuated a second time, so
the ground goes black while the coral, which carries its own material, stays
lit above it.

Taking the water back out is done and is not the answer. Red is gone in four
metres, so the red band of a picture of a reef in fifteen holds no bottom
signal at all — there is nothing there to recover, and no exponent of the right
shape recovers it. What survived is *structure*: where the sand is, where the
coral is, where the rubble is. That is worth having and it is not colour.

So the colour has to come from what a thing *is* rather than from what it
photographed as. The imagery classifies the bottom; the class carries the
colour, against real references, the way the coral prototypes already do. The
zonation model already reads the picture to tell rock from sand — this is that
same reading, carried through to the surface rather than stopping at how much
coral to plant.

The deep site is a separate problem and a smaller one: it is six hundred metres
of open water and there is nothing in it to look at, which is true of the place
and not a defect of the rendering. What it needs is not a better seabed but a
reason to point a camera.

**Done when:** somebody who dives reefs looks at a frame from Al Fahal and does
not ask what is wrong with it.


## 51. The rest of the fleet

Two vehicles are published and KAUST operates more than two. The catalogue also
holds `bluerov2-heavy` and `remus-100` as files that were never published, so
no dive can ask for either — a package nobody pinned is a package that does not
exist.

What is missing, and what it costs:

  **Ocean Aero Triton.** The one they signed an agreement for. A hundred metres,
  two knots submerged, wind and solar, ten days under and thirty on the surface.
  A thruster vehicle, so it slots in beside the BlueROV2 and the work is a
  package rather than a physics model. Worth having because its two knots is
  the same speed as the water in our own matrix: a Triton in that current makes
  no headway at all, and being able to show that is the point.

  **Maritime Robotics Otter.** Sixty-five kilograms of catamaran, two Torqeedo
  outboards, six knots, twenty hours. This is the interesting one, because it
  is a *surface* vehicle and we have never had one. The surface itself is
  already modelled — the submerged fraction, the buoyancy a hull loses as it
  emerges — and nothing uses it. A vehicle that lives at the surface rather
  than passing through it needs the sea state we do not have: a hull that
  pitches in a swell, and a survey whose quality depends on it.

  **The work-class ROVs on RV Thuwal.** Not modelled and not modellable yet:
  the press releases name the capability and never the hull, and the models are
  in the methods sections of papers behind the usual doors. Asking KAUST is the
  short way and is ruled out for now.

**Done when:** a dive can be flown by every vehicle KAUST actually operates
that we can honestly describe, and the ones we cannot are named as such rather
than quietly absent.


## 52. The study map: a place somebody laid out themselves

*Builds on:* 25, which already lets a place carry objects at known positions
and the tasks score against them. What is missing is not the idea of a thing in
the water, it is any way to put one there without editing JSON.

A place is bathymetry and coral, and both are read from a survey. That is the
right foundation and it is not a site. What a dive actually happens in is a
site somebody *arranged*: an array laid in a particular pattern, a ship holding
station over there, a nursery frame here, a line running between those two
points, a thing dropped on the bottom to be found again.

None of that can be expressed today. Conditions vary the water and the
vehicle's own fit — current, visibility, salinity, which instruments are
shipped, what fails and when — and every one of those is a *parameter*. The
world itself is fixed, so the questions that can be asked of it are fixed too,
and that is the whole reason `what-if` sweeps numbers rather than situations.

**It is a drawing problem and it does not need a 3-D editor.** Everything in
the sea is placed on a bottom whose depth is already known at every point, so a
plan view plus a depth readout is enough to place anything: the operator works
in two dimensions and each tool resolves the third from the ground under it.
Build a 3-D scene editor and the cost is a year and a modelling skill nobody
running a reef programme has.

So: the site's bathymetry drawn as a chart, depth under the cursor, a palette
down one side, and every tool carrying its own rule for how it meets the
bottom —

  **sits on the ground** — a mooring block, a transponder, a nursery frame, a
  crate: take the depth under the point and stand the thing on it.
  **floats at the surface** — a ship, a buoy: z is zero and the thing has a
  draught, and if it carries a USBL then the array's position follows it.
  **runs between two points** — a line, a cable, a tether, the edge of a
  net: drawn as a polyline on the chart and hung as a catenary between the
  depths at its ends, which is what a rope in water does.
  **stands up from the ground** — a column, a piling, a marker post: a base
  depth and a height.
  **a region** — a restoration cell, an exclusion zone, a work area: a polygon
  on the chart, which is what a grid cell already is and is drawn by hand
  rather than derived from a task.

Saved as an overlay on the place, versioned and pinned the way everything else
is, so two dives in the same laid-out site are comparable and a site somebody
arranged in March can be flown again in September. The place package stays the
survey; the study map is what was put in it.

Then the structural half of `what-if` becomes possible for the first time —
not "what if the current is half a knot" but "what if the mooring line is
where the chart says it is, and what if it is not".

A drawing tool is not a drawing until it can be edited. Select, move, delete,
duplicate, nudge by a stated number of metres, undo, copy a whole layout to
another part of the site, rename, group. A restoration lays out fifty nursery
frames on a grid and moves the lot three metres left; a tool that can only add
makes that fifty-one operations and a reason to use something else. The place
where this is usually got wrong is duplication — a copied array has to come
with new identities, not new references to the same transponder.

**Done when:** somebody who has never opened a 3-D tool lays out an array, a
ship, a nursery and a line across a real reef in a few minutes, moves half of
it, duplicates the rest, saves it, and two people fly the same arranged site.


## 53. Things in the water that move, and the tether that pulls back

*Not the same as 29.* That is the vehicle going wrong on a clock — a thruster
dead at two minutes, sensors quiet for five seconds. This is the world moving
whether or not anything has failed. A dive wants both and they are different
machinery.

Once a site can be laid out (52) the things in it have to behave, and the
cheapest correct model is not the obvious one. A lumped-mass dynamic cable is a
month and it is the wrong month.

What is actually true of a line in the sea:

  **Waves die with depth, fast.** Water particle motion falls off as
  e^(-2πz/λ), so a sixty-metre swell has moved four per cent as much at thirty
  metres as it has at the top. Below half a wavelength there is effectively no
  weather. A line in forty metres of water whips at its top and is still at its
  bottom, and modelling the whole thing as either rigid or thrashing is wrong
  at one end or the other.

  **Wind never touches the line.** It moves what is holding it — a ship, a
  buoy — and that travels down. A vessel yawing on its anchor drags a whole
  catenary with it, which is the honest reason a transponder is not where it
  was laid.

  **Current is the one that matters, and it is not oscillation.** A line drags
  downstream and takes a bow. A vertical mooring in half a knot is not
  vertical, the displacement is metres, and it persists — which is exactly the
  thing that makes an object *not where the chart says it is*, and therefore
  exactly the `what-if` worth asking.

  **A cable in current hums.** Vortex shedding, small amplitude, high
  frequency. Worth knowing about; not worth simulating here.

So: a quasi-static catenary that bows with the current, and surface-driven
motion applied only in the top half-wavelength. Metres of displacement where
metres matter, and no solver.

**And the one that is not scenery at all.** A BlueROV2 is tethered and we do
not model the tether. A hundred metres of it streaming in a current has far
more area than the vehicle does, so the tether's drag is often the larger force
— a small ROV working down-current is mostly fighting its own umbilical. That
is not an obstacle to avoid, it is a term in the equation of motion, and it
changes how every tethered dive in this record would have flown. It should be
built before any of the rest of this, because it is the only part that is
already wrong rather than merely absent.

**Done when:** a mooring laid at a stated position is somewhere else in a
current and the record says by how much; and a tethered vehicle with a hundred
metres out flies measurably differently from one with ten.


## 54. What a place can hold, and what it cannot

The study map (52) is the same editor over Al Fahal and over Thuwal Deep, and
it must not offer the same palette. A nursery frame in six hundred metres of
open water is not a scenario, it is a mistake somebody will make on a Tuesday;
a diver at that depth is not a hazard to model, it is a misunderstanding. And
the other way: a profiling float in fifteen metres of reef has nowhere to go.

So a place declares what it can hold, and both the editor and the runtime read
that declaration — the editor to decide what to offer, the runtime to decide
what to bother simulating.

  **Al Fahal, nought to sixty metres.** Holds nursery frames, mooring blocks,
  marker posts, settlement tiles, instrument packages standing on the bottom,
  lines run between them, restoration cells drawn as polygons, transponders for
  an array, a small boat, and divers. Simulates bottom work, a camera that can
  see, a sonar with something to return off, a Doppler log that has a bottom to
  lock to, silt raised by the vehicle's own thrusters, surge over the crest,
  the tether, and things alive in the water. Does not hold a glider: it cannot
  hover, it will not work above ten metres of altitude, and there is not enough
  water under it.

  **Thuwal Deep, five hundred to six hundred and forty metres.** Holds a ship
  holding station, a surface buoy carrying a USBL, a deep mooring with
  instruments hung at stated depths, a drifter, and the line of a section. No
  divers, no bottom work, no nursery — the bottom is six hundred metres down
  and nothing we operate goes there. Simulates the water column as the thing
  that matters: temperature and salinity against depth, a current that is not
  one vector but a different vector at every depth, surfacing for a satellite
  fix, and shipping — this is one of the busiest lanes in the world and a
  glider surfacing into it is a real way to lose one. It does not need a
  camera at all, which is not a limitation of the site but a fact about it:
  the first glider dive flown there recorded forty-three minutes of blank blue
  water, correctly.

Two things fall out of this that are worth having on their own. **A current
that varies with depth** — ours is one vector for the whole column, which is
fine over a reef in fifteen metres and wrong in six hundred, where the shear
between layers is the science a glider is sent to measure. And **shipping**,
which is the only hazard on that site and has no equivalent on the reef.

**Done when:** the editor over a reef and the editor over open water offer
different tools without anybody having configured that by hand, and a place
that cannot hold a thing says so rather than accepting it and simulating
nothing.

*Overlaps, resolved:* this, 55 and the refusal already built in 42 are one
mechanism written three times — a thing declares what it is for, a thing
declares what it needs, and the mismatch is refused before the dive rather than
discovered during it. It exists once already: a task says `needs_hover`, a
vehicle says whether it can, and a glider asked to hold station is told. That
is the pattern; a place's palette and a vehicle's kind are the same pattern
over different nouns, and they should be **one declaration and one refusal**,
not three. Build it once here and let 55 and 56 use it.

## 55. What a vehicle is, and therefore what it can be asked

A vehicle is not a set of numbers, it is a *kind*, and the kind decides more
than the numbers do. The platform already learned this once the hard way: a
glider was offered the hold controller, which commands a wrench on a hull with
nothing to produce one, and the answer was not a controller holding station
badly — it was a controller doing nothing at all while the vehicle fell. Four
kinds, and the differences between them are not tuning:

  **Hovering.** BlueROV2, and its Heavy. Stops, holds a position, works close
  to something. Tethered, so it has an umbilical that is the largest drag on
  it and a hard limit on how far it goes. Two hours. This is the only kind that
  can plant a coral or inspect a structure — the tasks that need the vehicle to
  *stop* all need this kind, and that is already enforced by `needs_hover`.

  **Flying, powered.** REMUS 100, sitting unpublished in the catalogue. One
  propeller and fins: it cannot stop, cannot hold a depth without moving, and
  cannot back up. What it can do is cover ground — eight hours of lawnmower at
  a metre and a half a second, which is the survey workhorse of the industry
  and a thing we cannot currently fly. Between the ROV and the glider in every
  respect, and absent from all of it.

  **Flying, unpowered.** The Seaglider. Months, a quarter of a metre a second,
  and beaten by anything over 0.4 m/s. Built.

  **Surface.** The Otter, and the Triton when it is up. Never submerged, or
  submerged only sometimes, and the thing that makes it different is that it
  lives where the weather is: a surface vehicle in a sea state is a vehicle
  that pitches, and a survey flown from one is only as good as that.

Two of the four are published. The Heavy is the one that would repay the least
work: eight thrusters against six, four of them vertical, which makes it the
only vehicle here with pitch and roll authority — six degrees of freedom where
the standard hull has four. That is not a footnote for photogrammetry, where
holding attitude *is* the job, and it is a package rather than a physics model.

**Done when:** each kind is published and flying, a task that needs a kind the
vehicle is not says so before the dive, and the catalogue holds no package that
no dive can ask for.

*Overlaps, resolved:* the refusal half of this is 54's single mechanism — do
not build a second one. What is left here is the work that is genuinely its
own: publishing the Heavy and the REMUS, and modelling the Triton and the
Otter. The Otter is the one that is not just a package, because a surface
vehicle needs a sea state to live in and there is none (53).

## 56. Sensors that are more than declared

The BlueROV2's package names five instruments. Three of them do something.

  **The camera** works: it renders, and its field of view is what a survey's
  lanes are spaced by — the one place where getting a sensor's geometry wrong
  cost a task forty per cent of its score.

  **The Doppler log** works, and properly: a bottom-lock range, a scale error
  drawn once per dive, noise. Losing it is the single worst thing that can
  happen to an outplanting, and the sweep says so.

  **The depth gauge** works, and since the water gained a density it can be
  wrong in the interesting way: calibrated for the wrong sea it reads a fixed
  fraction deep, which is a bias rather than noise.

  **The imaging sonar is declared and nothing happens.** A hundred and thirty
  degrees, half a metre to ten, and there is nothing in the world for it to
  return off — no obstacle, no structure, no line, no bottom return. A forward
  sonar that cannot be wrong is not a sensor, it is a line in a manifest. It
  becomes real the moment 52 puts things in the water, and not before.

  **The IMU is half there:** a heading bias it keeps all dive, and no rates, no
  drift, no bias walk.

And two that are missing outright. **A CTD** — the Seaglider's package declares
one and it measures nothing, which is absurd on a vehicle whose entire product
is temperature and salinity against depth. The water now has both, computed at
every depth; an instrument to read them is a small piece of work and the
difference between a glider mission and a glider-shaped trajectory. **Lights** —
there are none, so every dive is lit by the sun and a night survey, which is
routine work, cannot be posed.

Sensors are also a question of place, the way vehicles are (54). A camera in
six hundred metres sees nothing. A Doppler log needs a bottom within fifty
metres, so over the deep site there is no bottom lock at all — which is not a
detail, it is why the glider dive drifted nine hundred metres and why that
drift is the measurement.

**Done when:** every instrument a package declares does something a dive can
notice, and an instrument that cannot work where the dive is says so.

*Depends on:* the sonar half cannot be built before 52 — a sonar needs
something in the water to return off, and until a place can be laid out there
is nothing. The CTD and the lights do not: both can be built now, and the CTD
is the smaller and the more valuable, because the water already has a
temperature and a salinity at every depth and a glider's entire product is
reading them.

## 57. The map says where, the task says what counts

*Depends on:* 52. Geometry has nowhere to live until a site can be drawn.

A task carries two things that are currently one, and separating them is what
makes a laid-out site (52) worth laying out.

  **Where.** Which cell, which marks, which line, which thing. Geometry.
  **What counts as done.** Planted within a tolerance, covered at an altitude
  steady enough to reconstruct from, held for three hundred seconds, found.

Today both are in the objective, and the geometry is written as offsets from
wherever the dive happened to begin — `dx`, `dy`, a cell of a stated size. It
has to be, because there is nowhere else for geometry to come from. Which is
why nobody can say *plant at these thirty-five positions, on this reef*: the
task invents its own positions relative to a start, and the start is not a
place, it is an accident of where the vehicle was put.

Once a site can be drawn, that inverts. The map holds the geometry and the
things in it have identities; a task is a kind plus a reference to what was
drawn. A nursery frame somebody placed is scenery, and the thing to inspect,
and the thing to keep clear of, depending only on which task points at it.

**Users compose missions; they do not write scoring rules.** A mission as an
ordered sequence of stages already exists — survey, dock, charge, survey, each
scored on its own line. Let anybody build those, over any geometry they drew.
But a task *kind* is a mark scheme, and a platform where every user writes
their own mark scheme has no comparable results in it at all, which is the one
thing this is for. New kinds are ours to add, deliberately, and the reason to
add one is that somebody's real job needs a rule we do not have — which is how
outplanting and monitoring arrived.

**A free dive is a mode, not an absence.** It half exists: a dive with no
objective, flown by hand, scored on nothing. It reads as a degenerate case and
it is not one. Opening a site somebody laid out and simply flying it is how
anybody gets the feel of a place, it is the most convincing thing to put in
front of a person in a room, and everything about it should still be recorded
— the track, the video, the energy — so that a free dive can be replayed and
argued about like any other.

**The thing to get right.** A dive currently pins one versioned artefact for
the world, the place's package. With a layout it pins two, and if the layout is
not pinned as hard as the place is then two runs of "the same mission" are
quietly not, and every comparison built on them is worthless. The layout is a
version of the place or a version beside it — either is defensible — but it is
versioned, digested and pinned, exactly like everything else.

**Done when:** a task can be pointed at something somebody drew rather than at
an offset from the vehicle's start, a mission can be assembled from stages over
that geometry, a free dive can be flown in the same site and replayed, and a
run names both the place and the layout it was flown in.


## 58. Ground as fine as the work is

Al Fahal is five hundred and twelve samples over three kilometres: **5.9 metres
between depth samples**. The outplanting flown over it scores position to a
metre and holds altitude in a band of sixty centimetres, over a bottom that is
straight-line interpolation across six metres of ground. Real reef relief at
that scale is metres — spur and groove is exactly a structure of that size —
so a controller is being scored to centimetres against a seabed that does not
have the shape it would really have, and one that learned to fly here would
meet a surface it had never seen.

The mismatch is between the *site* and the *task*, so either end can give.
Finer ground where the work is: a site does not need six metres everywhere, it
needs centimetres over the cell being planted and metres over the rest, which
is a patch at a second resolution rather than a bigger grid. Or the tasks admit
what they are standing on, and a tolerance finer than the ground refuses
itself.

Both, probably. The first is what makes a close-up dive worth watching; the
second is what stops a number being quoted that the ground cannot support.

**Done when:** a task cannot ask for a tolerance the ground it is over cannot
answer, and a cell somebody is planting can be carried at a resolution that
makes the answer mean something.


## 59. A result knows what computed it

A run pins its place, its vehicle and its conditions by digest, and nothing at
all about the simulator that produced it. Today the thruster geometry moved,
the depth loop was retuned, the attitude guard changed hands, dead reckoning
stopped seeing through the water, and a working stop stopped counting as
reached before the vehicle got there. Every one of those changes what a dive
does. Every result from before is incomparable with every result after, and the
record does not say so anywhere.

That is a quiet correctness hole in a platform whose product is comparison. It
does not announce itself: the numbers still line up in a table, the grid still
renders, and two rows that cannot be compared look exactly like two rows that
can.

A run should carry the runtime's own identity the way it carries everything
else — the image digest at least, and better, a short statement of the physics
that actually bears on a result. Then a comparison across a change can be
refused, or flagged, rather than quietly made.

**Done when:** two runs from either side of a physics change cannot be put in
the same table without the platform saying so.


## 60. Something comes out of it

A monitoring programme's deliverable is data. Ours is a score and a video.

Nobody can take *where the two million corals went* out of this and use it —
the outplanting knows, to the centimetre, and it is a list inside a JSON
document inside a run. The same for the colonies a monitoring pass imaged, the
coverage map it built, and the profile a glider brought back, which does not
exist at all yet because there is no CTD (56).

The question is not "can it be exported", it is what a reef programme would
actually open: positions and identities of what was planted, as something a GIS
reads; a coverage map of a cell as a raster with a datum; a colony inventory
with what was seen and when; a profile as the column against distance. Formats
that already exist, because a deliverable in a format we invented is not a
deliverable.

**Done when:** somebody who does not have this platform can open what a dive
produced, in a tool they already use, and do something with it.


## 61. Time of day, tide, and season

Light is a function of depth and nothing else — one exponential from the
surface. There is no hour, no sun angle, no night. A night survey is routine
work and cannot be posed at all, and there are no lamps to pose it with (56).

There is no tide, so there is no reason the water over a reef flat is ever
different, and on a shallow reef the tide is the difference between a working
day and a lost one. And there is no season, which for a restoration is the
strangest omission of the three: coral spawning is a **date**, KCRI's year is
built around it, and a mission planned for the wrong week is a mission that
missed the thing it was for.

**Done when:** a dive can be planned for a date and an hour, and the answer is
different for it.


## 62. Somebody who dives says it is right

Everything here is self-consistent. The equations are the published ones, the
bathymetry is from a survey or honestly labelled as not, the vehicle's numbers
come from its manufacturer, and every result agrees with every other result.
None of that is evidence.

The thruster position was wrong for weeks and nothing caught it, because
nothing in a self-consistent system can. What caught it was flying a task that
could not be done and asking why — and a person who has actually driven an ROV
over a reef would have said "that doesn't handle like that" on the first
afternoon.

This is not a feature and it is the thing the platform's credibility rests on:
one dive, watched by somebody who does the real thing, who is asked what is
wrong with it. Cheap, and it cannot be done by us.

**Done when:** somebody who has flown a vehicle in that water has watched this
fly in it, and what they said has been written down here.


# The order to build it in

The list above is what, and it is numbered in the order the items were thought
of rather than the order they can be done. This is the order they can be done,
and why each one has to wait for the one before it.

Three things are true of the whole plan and worth saying once. **Nothing below
has a user interface**, and everything built in Phase 5 is driven from a
terminal by the person who wrote it — a rehearsal system a programme actually
uses is a screen, and the screen is not optional work to be done afterwards.
**A platform whose product is comparison cannot change its physics silently**,
which is why 59 comes before the rest rather than after. And **none of it is
evidence until somebody who dives says so** (62), which can be arranged at any
point and gets later and more embarrassing the longer it is left.

---

## Now, because everything else quietly depends on them

- [ ] **59 · a result knows what computed it.** Small, and every day without it
      more results become unsafe to compare. Nothing else should land first.
- [ ] **49 · a model actually flies a dive.** Built, wired, never run. One
      deploy. Until it happens, "AI controller" is an assertion and the
      benchmark has one contestant.
- [ ] **50 · the map stops looking wrong.** Colour from what a thing *is*, not
      from what it photographed as. The satellite cannot say what colour coral
      is and it can say clearly where it is.

## Then the foundation the rest of it stands on

- [ ] **54 · one declaration and one refusal.** A thing says what it is for, a
      thing says what it needs, a mismatch is refused before the dive. Exists
      once already (42); generalise it rather than write it twice more.
- [ ] **52 · the study map.** The 2-D editor: draw on real bathymetry, depth
      under the cursor, a landing rule per tool, and the editing that makes it
      a tool rather than a demo. *This is the largest single item in the list
      and the one the most others are waiting on.*
- [ ] **57 · the map says where, the task says what counts.** Needs 52 to
      exist. Splits geometry from scoring, which is what lets a mission be
      designed rather than parameterised.
- [ ] **53 · the tether.** Out of order on purpose: it needs none of the above
      and it is the only thing in this list that is already *wrong* rather than
      merely missing. Every tethered dive in the record flew without the
      largest drag force acting on it.

## Then the things that become possible

- [ ] **53 · the rest of it** — catenaries that bow with the current, motion in
      the top half-wavelength, things that move.
- [ ] **56 · the sonar,** which needs 52 to have put something in the water.
- [ ] **56 · the CTD and the lights,** which need nothing and should not wait.
- [ ] **58 · ground as fine as the work.** Once tasks are drawn on a map, the
      map's resolution stops being a detail.
- [ ] **55 · the rest of the fleet.** Publish the Heavy and the REMUS first —
      packages, not physics. The Otter needs a sea state and waits for 53.
- [ ] **61 · time of day, tide, season.**

## Then the reason any of it was built

- [ ] **the structural what-if.** Not "what if the current is half a knot" but
      "what if the mooring is not where the chart says". Only possible after 52.
- [ ] **60 · something comes out of it.** A deliverable a reef programme opens
      in a tool it already has.
- [ ] **46 · overlap,** the third thing a reconstruction needs.
- [ ] **47 · census,** which wants coral to have a condition.
- [ ] **48 · a dive flown from words,** end to end.
- [ ] **37 · the benchmark,** which has been waiting for a second contestant
      since Phase 4 and gets one from 49.

## Running alongside, not after

- [ ] **the interface.** Every item above has a screen it needs and none of
      them have one: laying out a site, assembling a mission, reading a sweep,
      watching a replay, exporting a result. Built as each item lands, or it
      becomes a second project that never starts.
- [ ] **45 · calibrated depths.** One free account and ICESat-2 makes Al Fahal
      measured rather than plausible. Not ours to create.
- [ ] **62 · somebody who dives says it is right.** At any point. The longer it
      waits the more there is to be wrong about.


## What a dive is made of

Six things, chosen separately, crossed at the moment somebody presses Dive.
Keeping them apart is not tidiness: it is the only way one task can be flown
on four technologies, or one controller judged across five waters, and the
results mean anything.

  **The place.** A city and a published version of its package: the bottom as
  a height field, the coral where the survey found it, the textures, and what
  the site says about itself. Versioned, pinned by digest on every run.

  **The vehicle.** A vehicle and a published version: mass, buoyancy, inertia,
  added mass, damping, thrusters and where they point, the sensors it carries,
  the battery it carries, and the instruments it navigates by. Also versioned
  and pinned. Nothing about a dive is written into it.

  **The technology it knows where it is by.** Two halves that belong to two
  different people, and they must not be one thing. What the vehicle carries
  is the vehicle's, stated by whoever published it. What is *deployed in the
  water* — a ship overhead with a USBL, an array of transponders on the
  seabed, nothing at all — is the situation's. A dive may also unship what the
  vehicle has: the same hull without its Doppler log is a different problem
  and should not need a second vehicle in the catalogue.

  **The water.** What the sea is doing: the current as a speed and a heading,
  how far you can see, and anything that is going to go wrong on purpose — a
  thruster at two minutes, the sensors quiet for five seconds, a gust. Held as
  a conditions document, named, versioned, pinned by the run.

  **Who flies it.** A person at the keys, the platform's own guidance, or a
  stack somebody wrote and deployed as an image pinned by digest. The helm
  decides between them every step, and one thing outranks all of them: the
  failsafe, which is watching whether the job can still be paid for.

  **What it is for.** An objective: a task, or a mission of several stages.
  Scored as the dive runs, against the truth, and reduced to a result with the
  energy it cost.

The line that matters most runs between the last two and everything else. A
controller is handed what the vehicle *knows* — a position dead reckoned from
a Doppler log and a compass, a heading that is a degree or two wrong, a depth
from pressure — and never what is true. The task is scored on what is true.
The gap between those two is underwater navigation, and it is why a reach of
sixty metres is a real task rather than a straight line.


## Not on this list

Batch across many conditions. It is the same objective machinery from item 4,
evaluated many times with nobody watching, and building it before the objectives
exist would mean two definitions of what a good dive is.
