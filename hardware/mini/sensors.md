# mini-hoot: sensing for navigation and collision avoidance

For a tank: iocean-tank-1 now (2 × 1 × 1 m of glass), a public aquarium later.
One pick per job, and what it costs the vehicle.

| Job | Pick | Why this one | Numbers (datasheet unless marked) |
|---|---|---|---|
| Where am I | **Overhead camera** tracking an AprilTag on the lid (tank); **Water Linked Underwater GPS G2** with a U1 locator (large aquarium) | A tank is small and lit, so a camera above it is the best positioning there is. A large aquarium is deep and seen by the public, so an acoustic short-baseline system takes over: it is made for tanks and pools | camera: 5 mm, 10 Hz (chosen). UGPS G2: <0.2% of horizontal range, <1° angle, <1% depth |
| How fast am I moving, how high off the bottom | **Water Linked DVL A50**, under the belly, looking down | Velocity over the ground and altitude from one 66 × 25 mm puck; works down to 5 cm, which a tank needs | 66 × 25 mm, 170 g in air, 105 g in water, 5 cm to 50 m, 4–15 Hz, four beams at 22.5° |
| What is in front of me | **Blue Robotics Ping2** echosounder, under the nose, looking forward | One beam ahead gives the range to the glass, a rock or the fish wall coming at it. A scanning sonar (Ping360) sees all round but is the size of the vehicle | 71 × 47 × 41 mm, 187 g in air, 100 g in water, 25° beam, 115 kHz, 5 V |
| What exactly is it | The **camera** behind the dome | A sonar says something is there; the camera says it is coral, glass or a fish, and the DGX does that part | already fitted |

## What this costs

About 360 g more in air and 205 g more in water, all of it low on the
vehicle. That is lead it no longer needs: the trim goes from about 320 g of
lead to about 110 g, and the righting arm improves because the weight moved
down.

## What it will not do well, said now

- **Acoustics in a glass box echo.** A 2 m tank is a reverberant room for a
  115 kHz ping: the forward echosounder will see the far glass, the near
  glass and the floor in the same beam, and its shortest reliable range is
  about 0.3 m (assumed until measured in the tank). Close in, the camera and
  the map carry the avoidance; the sonar is the far warning.
- **A DVL needs a bottom.** Over the rock it reads the rock, over the sand the
  sand; that is altitude, not depth, and it is what the floor clamp needs.
- **The overhead camera loses the tag** under the gantry and under a rock
  overhang. The DVL carries the position across those gaps.

## In the simulator

Each pick is a sensor in mini-hoot's package with these numbers, the
forward echosounder ranging against the tank's glass, its rock and its
floor; the DVL against the floor and rock. The avoidance flies on the
echosounder and the map, and the score says whether anything was struck.
