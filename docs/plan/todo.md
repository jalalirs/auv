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

## 2. A vehicle that starts still

A dive begins with the vehicle stationary at the start point for its task,
holding depth and heading, not sinking.

This is not a spawn position — it is a capability. A real ROV is slightly
buoyant and holds depth on its thrusters, so the vehicle needs a **hold**: a
station-keeping controller of its own that maintains the pose it was placed at
and lets go the moment a pilot or an autonomy stack commands anything. Without
it every dive begins by falling.

**Done when:** a dive opens, the vehicle sits where it was put for a minute
without drifting more than a few centimetres, and the first key press or first
ROS command takes it cleanly.

---

## 3. The cockpit

The channel protocol, and what it makes possible.

- `hello`, `view`, `frame`, `pose`, `topic`, `event`, `control`, `objective`
- Views: chase, free, top, front, vehicle camera, sonar — any as the large pane
- Minimap and top view drawn on the client from pose and the site outline
- The topic tree live on every dive, with rates and counts, and a visualiser per
  topic type

**Done when:** four views can be open at once, the minimap shows the vehicle
moving over the site with its track behind it, and clicking `/depth` opens a
plot of it.

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

---

## 5. Data collection

A survey's product is the data. Frames, poses, and sensor output recorded to the
run's artefacts, with coverage computed from where the camera actually looked.

**Done when:** a survey dive leaves a recording that can be listed, fetched and
replayed, and its coverage is a number derived from the poses rather than an
assertion.

---

## 6. Fly all of it

Manual dive through the finished thing: start still, take the controls, run a
task, be scored, leave, and have the machine given back.

**Done when:** you do it and it is not annoying.

---

## Not on this list

Batch across many conditions. It is the same objective machinery from item 4,
evaluated many times with nobody watching, and building it before the objectives
exist would mean two definitions of what a good dive is.
