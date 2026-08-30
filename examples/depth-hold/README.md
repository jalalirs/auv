# Depth hold

An autonomy stack, written the way somebody bringing their own would write it.

It imports nothing from Coral City and knows nothing about a simulator. It
subscribes to `/depth`, works the depth out of the pressure the way it would
from a real sensor, and publishes six thruster commands on `/thruster_cmd`.
The same container would fly a real BlueROV2.

That is the whole claim the platform makes, and this is what tests it.

## Running it

```bash
docker build -t registry/depth-hold:v1 .
docker push registry/depth-hold:v1
```

Then register it and pin it by digest — never by tag, because a dive re-run
against a tag that has moved measures a different program and reports it as the
same one.

## What it does not do

No deadband, no buoyancy feed-forward, no integral term, so it settles a little
below its target and stays there. Making it good would make it longer and worse
as an example: what is being shown is that a program nobody here wrote can fly
this vehicle, not how to write a good controller.
