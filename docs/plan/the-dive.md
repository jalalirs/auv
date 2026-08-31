# The dive

What we are actually building, so that the pieces stop being pieces.

We have a platform: identity, grants, a catalogue, queues, an agent, packages
pinned by digest, a control plane that refuses what it should refuse. We have a
physics loop that is right. We have a client that connects. What we do not have
is a **simulation environment** — somewhere you go, in a vehicle, to do
something, and can see what is happening from every angle you need.

This describes that. It is not a wish list; it is the shape the code should
take, and everything below is either built, half built, or explicitly next.

---

## A dive is four things

**A site** — where you are.
**A vehicle** — what you are in.
**An objective** — why you are there.
**An observer** — who is watching, and through what.

Every design decision below belongs to exactly one of those, and the reason the
current thing feels like pieces is that three of the four barely exist.

---

## 1. The site

A place is not a USD file. It is a stack of layers, versioned together:

| layer | what it is |
| --- | --- |
| **terrain** | bathymetry — the seafloor, at whatever resolution the source had |
| **structures** | coral, wrecks, moorings, pipelines, the things you go to look at |
| **water** | density, temperature, turbidity, light attenuation per wavelength |
| **current** | a field, which may vary with position, depth and time |
| **surface** | waves, and what light gets through them |
| **life** | fish and larger animals, scripted or agent-driven |

A site version pins all of them. That is already why a place is a package rather
than a file, and it is what makes "the same reef, one year later" a thing the
platform can express.

**Every site declares a datum and a spawn.** A dive begins at the spawn — the
centre of the site unless the dive names a waypoint. Today the vehicle starts at
`(0, 0, -2)`, which is wherever that happens to fall in whatever scene was
loaded, and in the tow tank it is nowhere near the middle. That is not a
cosmetic problem: a dive that does not begin somewhere meaningful cannot be
compared to another dive that also began nowhere in particular.

**The seafloor is solid.** A vehicle that reaches it lands on it. Today nothing
collides: an untended ROV falls through the floor of a 6.8 m tank and keeps
going, and at 22 m it is below the world, looking at nothing. Collision is not a
detail — without it there is no bottom, and without a bottom there is no
inspection, no landing, no altitude, and no station-keeping over anything.

---

## 2. The vehicle

Dynamics we have, and they are correct: added mass folded into effective mass,
quadratic drag, restoring moments, thrust allocated by pseudo-inverse. A
BlueROV2 settles at the terminal velocity its own coefficients predict.

What is missing is that **sensors are not objects**. Three publishers are
hard-coded into the boundary. A sensor should be a thing with:

- a pose on the hull
- a rate of its own
- a ROS 2 message type
- noise, and limits, that are part of the vehicle's published parameters
- a visualiser in the cockpit that is chosen by its type

The suite this platform is for: **depth**, **IMU**, **DVL**, **altimeter**,
**mono and stereo camera**, **imaging sonar**, **multibeam**, **USBL**. Plus
what a vehicle does rather than senses: **thrusters**, **lights**, and later a
**manipulator**.

The vehicle's topic contract — which already exists and is already checked
before a dive is admitted — becomes the list of its sensors, rather than a
separate declaration that has to agree with one.

---

## 3. The objective

A dive has a purpose, and the purpose decides what "well" means. There are four
kinds and they are genuinely different, not settings on one thing.

**Piloted.** A person flies it. There is no score. What matters is that it feels
like a vehicle in water and looks like somewhere real.

**Mission.** Autonomy is given tasks — reach these waypoints, hold this station,
follow this transect, inspect this structure, come home. The platform evaluates
each: reached or missed, how close, how long, how much energy, whether it ever
lost control. A mission is a list of tasks and a rule for when the dive is over.

**Survey.** Fly a pattern and record. The product is the data, not the
trajectory, so it is scored on coverage and quality — what fraction of the
target area was seen, at what resolution, from what angles.

**Replay.** A run pins its site, vehicle, autonomy, water, seed and runtime, so
it can be executed again and produce the same trajectory. Separately, a
recording can be played back without executing anything.

The objective belongs to the dive definition, is evaluated by the runner as it
goes, is published as progress while the dive runs, and is reduced to a result
at the end. Scored batch — the thing the roadmap called M7 — is this, applied to
many sets of conditions at once. It is not a separate feature.

---

## 4. The observer

The cockpit. This is the part that is furthest from where it needs to be.

### Views

| view | what it is for |
| --- | --- |
| **chase** | behind and above, following. The default, and how you fly. |
| **free** | orbit and fly anywhere. For looking at the site. |
| **top** | orthographic from above. Where you are. |
| **front / side** | orthographic. Attitude, clearance, trim. |
| **vehicle cameras** | what the robot sees — which is what the autonomy sees |
| **sonar** | the fan, as the sonar produces it |

Any of them can be the large one; any can be a small pane beside it. A layout is
which views are open, where, and at what size.

### The map is not video

The **minimap** and the **top view** are drawn on the client from the site's
outline and the vehicle's pose. Not rendered on the GPU and streamed as pixels.

This matters more than it sounds. It makes them sharp at any size, interactive
(click a point to set a waypoint), and free — and it means they keep working
perfectly when the video is slow or has stopped, which is exactly when a pilot
most needs to know where the vehicle is. A map that dies with the video is a map
you cannot trust.

Track, waypoints, the vehicle's heading, the extent of the site, and anything
the objective cares about all live there.

### Panels

Dockable, rearrangeable, and saveable as named layouts — *piloting*, *sensor
check*, *autonomy debug*, *survey*. The panels:

- **topic tree** — every topic, its type, its rate, how many messages have
  crossed. Click one and its visualiser opens: a plot for a scalar, an attitude
  ball for an IMU, an image for a camera, a fan for a sonar.
- **instruments** — depth, altitude, heading, attitude, speed, energy
- **thrusters** — what each is being asked for, signed
- **autonomy** — what is flying, what it last commanded, its task list
- **objective** — tasks, progress, what has been achieved
- **events** — a timeline, scrubbable after the dive

---

## 5. The protocol

This is the architectural core, and the current one is a hack that will not
grow: a single socket carrying JPEG frames of one fixed view, plus a JSON blob.

It should be **one connection carrying named channels**:

| channel | direction | what it carries |
| --- | --- | --- |
| `hello` | down | what this dive is; the views available; the topics; the site's outline and extent |
| `view` | up | open or close a named view, at a size |
| `frame` | down | encoded frames, tagged with the view they belong to |
| `pose` | down | vehicle pose and velocity, at a high rate, tiny |
| `topic` | up/down | subscribe to a topic; receive its messages |
| `event` | down | what happened, as it happens |
| `control` | up | what is held, or an axis |
| `objective` | down | task progress |

The property that makes this worth doing: **the client says what it is showing,
and the simulator renders exactly that and nothing else.** Two views cost two
render products. Nobody looking at the sonar means no sonar frames are encoded.
The map costs nothing because it is not rendered at all. And a slow link
degrades video while poses, topics and events keep flowing — so the instruments
stay live even when the picture stutters.

The transport can improve underneath — hardware-encoded video instead of JPEG,
WebRTC instead of a websocket — without the application changing, because the
channels are the contract and the encoding is not.

---

## 6. What this means for what exists

| now | becomes |
| --- | --- |
| vehicle starts at a fixed point | starts at the site's spawn |
| nothing collides | seafloor and structures are solid |
| camera fixed at the start position | named views, one of which follows |
| three hard-coded publishers | sensors with poses, rates and types |
| one JPEG stream of one view | channels, and views the client asks for |
| a HUD with two numbers | panels, layouts, and a map drawn from pose |
| `objective: {}` | tasks, evaluated and scored |
| conditions are "still water" | a current field, turbidity, light |

None of that is a rewrite. The physics does not change. The control plane does
not change. What changes is that the simulator stops being a thing that renders
one picture and starts being a thing that answers questions about a world.

---

## 7. Order

1. **One dive, right.** Spawn at the site's centre. The floor is solid. The
   camera follows. Fly it by hand with the keys and have it feel like a vehicle.
   Nothing else matters until this is true, because this is the thing being
   built.
2. **Views and the map.** The channel protocol, named views, the pose channel,
   minimap and top view drawn on the client.
3. **Sensors.** Camera and imaging sonar as real sensors, with visualisers, and
   the topic tree wired to them.
4. **Objectives.** Waypoints and station-keeping, evaluated live, scored at the
   end.
5. **Survey and recording.** Fly a pattern, keep the frames, score the coverage.
6. **The site.** Real bathymetry and real coral, which is a content pipeline
   landing on a platform that works rather than a rewrite.

Batch across many conditions falls out of (4): it is the same objective
evaluated many times without an observer.
