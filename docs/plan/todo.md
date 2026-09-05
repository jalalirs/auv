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
