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
console looks at with. Replay draws the track on a bare grid, since the
recording does not carry the site's map; it should.

---

## 6. Fly all of it

Manual dive through the finished thing: start still, take the controls, run a
task, be scored, leave, and have the machine given back.

**Done when:** you do it and it is not annoying.

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

## Not on this list

Batch across many conditions. It is the same objective machinery from item 4,
evaluated many times with nobody watching, and building it before the objectives
exist would mean two definitions of what a good dive is.
