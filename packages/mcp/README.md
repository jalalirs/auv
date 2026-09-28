# Coral City over MCP

Places, vehicles and dives an agent can drive, with every number marked.

```
CORAL_CITY_PLATFORM=http://your-platform:18080 \
CORAL_CITY_EMAIL=you@example.com \
CORAL_CITY_SECRET=... \
    python -m coral_city_mcp
```

Or `CORAL_CITY_TOKEN` instead of the email and secret. Credentials come from the
environment and never from a tool argument: an agent that can be told a password
in a prompt is an agent that can be told somebody else's.

## The point

Every value comes back as `{value, kind, from}`, where `kind` is one of
**measured**, **derived**, **chosen** or **assumed**. Asking about Al Fahal's
ground does not return `21.59`:

```json
"deepestM":      { "value": 21.59, "kind": "derived",
                   "from": "Copernicus Sentinel-2 S2B_T37QDE_20240223T080223_L2A" },
"calibratedToM": { "value": 5.0,   "kind": "derived",
                   "from": "ICESat-2 ATL24 v002 seafloor photons",
                   "note": "below this the fit does not hold and the ground is not calibrated" }
```

An assistant asked for a number will produce one, and that is the whole risk of
putting one between an operator and a decision. An assistant given *this* cannot
report the depth as a measurement without contradicting its own input — and it
cannot quote the 2.00 m rms of the fit without also being told the fit holds to
five metres.

A test walks every answer and fails if a bare figure appears anywhere in it.

## The tools

| Tool | Gives back |
| --- | --- |
| `places_list` | every place granted to this session |
| `places_get` | one place: ground, depth, what it is calibrated to, reef, water |
| `vehicles_list` | every vehicle, and whether it can actually fly |
| `controllers_list` | the autonomy deployed to this institution |
| `dives_list` | dives defined, newest first |
| `dives_result` | what a run scored — a run that did not finish is not a zero |
| `dives_deliverables` | track, coverage, planting, colonies, provenance |

`track.geojson` holds two features and they are not the same claim: where the
vehicle **was**, from the simulator, which is the only thing that knows — and
where it **believed** it was, from its own navigation. The distance between them
is the reason this exists rather than a video of a vehicle looking confident.

## Not here yet

`layouts_*` (draw a plot, render it as a chart an agent can look at),
`missions_create`, `dives_estimate`, `dives_start`, `sweeps_run`, `dives_frame`.

`dives_frame` waits on something real: no dive in the record has frames, because
they were all flown undrawn and the vehicle packages lost their hulls in a
republish.
