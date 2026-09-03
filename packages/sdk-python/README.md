# coral-city — the controller SDK

Write a controller for a vehicle in the catalogue, try it in a tank on your own
machine, put it on the platform, and fly it from the console. One class does
all three, and because nothing in it knows about a simulator, it is the class
that would fly the real vehicle.

## A controller

```python
from coral_city import Controller, Command

class Hold(Controller):
    name = "hold"
    vehicle = "bluerov2"        # which catalogue vehicle it is written for
    commands = "wrench"         # or "thrusters", if you allocate thrust yourself
    needs = ("dvl",)            # sensors it cannot do without

    def __init__(self):
        super().__init__()
        self.declare("depthM", 5.0, 0.0, 30.0, "m", "the depth to hold")

    def observe(self, seen):
        heave = 20.0 * (seen.depth - self["depthM"]) - 30.0 * seen.velocity[2]
        return Command.wrench_of(heave=heave)
```

`observe` is handed an `Observation` — position, body velocity, attitude,
depth, heading — and answers with a `Command`: a body wrench in newtons, which
the vehicle allocates across its thrusters, or per-thruster commands in
[-1, 1]. What `declare` names is what a hand can move while it runs: on the
platform's console, with a slider; over ROS 2, as a parameter with a range.

`self.described` is the vehicle as the catalogue describes it — thrusters,
sensors, topics, how much force it has on each axis (`.most`), how much it
floats — generated from the catalogue so what you check against is what you
will get. `examples/hold.py` is a station hold written this way.

## Try it

```bash
pip install -e 'packages/sdk-python[tank,dev]'    # from the repository
coral-city vehicles
coral-city check examples/hold.py
coral-city tank examples/hold.py --task hold --trace
```

The tank is the runtime's own hydrodynamics and helm, stepped headless without
Isaac Sim, as fast as the machine allows. By default the controller sees what
the vehicle's sensors would give it — pressure, attitude, velocity over the
ground, and a position dead-reckoned from them — through the same navigator
the live node uses. `--truth` hands it the true state instead.

Water that moves: `--current 0.51 90` on the command line, or
`Tank(..., current=(0.51, 90))`, is a knot flowing east, felt by the physics as
drag on motion through the water. A task scores the run in [0, 1] and gives a
reward per step, which is what a learner trains on — `examples/learn_hold.py`
does exactly that, finding a linear hold's weights in a current by the
cross-entropy method and writing them out as a controller to deploy:

```python
from coral_city.tank import Tank
from coral_city.tasks import ReachDepth

tank = Tank("bluerov2", task=ReachDepth(9.0))
seen = tank.reset()
while not tank.done:
    seen, reward, done, info = tank.step(policy(seen))
print(tank.report())
```

## Deploy it

```bash
./tools/box tunnel                              # in another terminal: the API and registry, on localhost
coral-city sign-in --api http://localhost:18080
coral-city deploy examples/hold.py --slug hold --name "Station hold" \
    --push-to localhost:18081 --pulled-from 127.0.0.1:18081
coral-city dive --stack hold --place looe-key --vehicle bluerov2
```

`deploy` builds an image on the ROS 2 distribution with the SDK and your file
inside, pushes it, and registers it — by digest, never by tag — as autonomy of
your institution, which is what lets every member define a dive with it. Say
what it needs beside the simulator and the scheduler will place the dive where
both fit, or say why it cannot: `--gpu-memory 8G` for a controller that is a
model, `--cpus 2 --memory 4G` for its processors and memory (the defaults). The
image links against nothing of the platform's. `dive` defines a dive with it
in a place, runs it, and prints what the runtime said: whether the stack
commanded, and where the vehicle ended up. `--interactive` keeps it up for the
console, where the controller's tunables appear as sliders beside the
runtime's own.

Live, the controller runs as a ROS 2 node (`python3 -m coral_city.ros
module:Class`): it subscribes to `/depth`, `/imu/data` and `/dvl/twist`,
publishes `/cmd_vel` or `/thruster_cmd`, and declares each tunable as a
parameter with a floating-point range. Any ROS 2 tool can move them; the
platform's console does.

## What a dive leaves behind

A dive that is for something records as it runs — poses at five hertz,
what its sensors said, how its task was going, and the frames it saw at one
hertz, looking down for a survey — and the platform keeps the recording as
the run's artefacts. Fetch it:

```bash
coral-city fetch <diveId> <runId> --into recording
```

`manifest.json` says what is there and how the task ended; `poses.jsonl`
carries the trajectory and which frame was taken at each moment; a survey's
coverage in the result is derived from those poses and the vehicle's camera
footprint, not asserted.

## What is generated

`coral_city/vehicles/*.py` come from `catalog/vehicles/*/dynamics.json`:

```bash
python3 packages/sdk-python/tools/generate_vehicles.py
```

Rerun it when a vehicle changes.
