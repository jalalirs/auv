"""A controller that learned.

A linear policy — a matrix from what the vehicle sees to the wrench it asks
for — with its weights found in the tank rather than written down. The
cross-entropy method: a population of weight matrices is sampled, each flies
the hold-station task in a current, the best tenth set the next generation's
mean and spread, and after enough generations the mean is the controller.

Nothing about this is deep, and it is not meant to be. It is the whole path a
researcher takes — a policy trained against the runtime's own physics on a
laptop, written out as a controller, deployed and flown on the platform and
scored against the hand-written hold — done once by us so it is known to work.
A network in place of the matrix is the same path with more parameters.

    python3 examples/learn_hold.py            # trains, writes examples/learned_hold.py
    coral-city tank examples/learned_hold.py --task hold --current 0.51 90
    coral-city deploy examples/learned_hold.py --slug learned-hold
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from coral_city.tank import Tank  # noqa: E402
from coral_city.tasks import hold_station  # noqa: E402
from hold_policy import FEATURES, LinearHold  # noqa: E402

# The water it learns in, and there is more than one of it on purpose.
#
# This trained at one knot from the east and nothing else, and the policy that came
# out was perfect there and poor everywhere — 1.000 at a knot, 0.210 in a gentle
# set, 0.139 in still water, against the hand-written hold's 1.000, 1.000, 1.000.
# It had learned a **bias, not a controller**: told to fight a knot from the east it
# pushes east whether the knot is there or not, and in calm water it pushes itself
# off station. "Learned 0.48 against hand-written 0.15" was true only at the one
# current both had ever been measured in.
#
# So each episode draws a current. A policy that scores well across the set has to
# work out what to do from what it *sees* rather than from what it was trained in,
# which is the whole difference between a controller and a constant.
WATERS = (
    (0.0, 0.0),        # still
    (0.13, 0.0),       # a gentle set, which is what the bench flies
    (0.51, 90.0),      # one knot from the east
    (1.03, 45.0),      # two knots, on the quarter
)
SECONDS = 30.0
LATENCY_TICKS = 3           # 150 ms at 20 Hz, about what the live loop has
POPULATION = 24
ELITE = 4
GENERATIONS = 14


def in_one_water(weights: np.ndarray, current, seed_shift: float = 0.0) -> float:
    """How well these weights hold station in this water: the task's score, less a
    little for thrust spent, so the cheaper of two holds that both stay put wins."""
    # Through the sensors and with the live loop's delay, or what is learned
    # holds in the tank and nowhere else — which is what the first policy did:
    # 0.48 here, 0.03 on the platform.
    tank = Tank("bluerov2", start=(seed_shift, 0.0, -7.0), seconds=SECONDS,
                task=hold_station(seconds=SECONDS, radius_m=0.5, depth_band_m=0.3),
                sensed=True, current=current, latency_ticks=LATENCY_TICKS)
    report = tank.run(LinearHold.with_weights(weights))
    # Thrust is dear: a policy that thrashes is penalised for it, since the
    # thrashing is also what does not survive a delay.
    return report.score - 0.3 * report.task["thrusterEffort"]


def rollout(weights: np.ndarray, seed_shift: float = 0.0) -> float:
    """Across every water, scored by its **worst** one.

    The mean would let a policy buy a perfect knot with a hopeless calm, which is
    exactly the trade the first one made. What a vehicle needs is to hold in
    whatever it finds, so the score is the weakest water it was tried in.
    """
    return min(in_one_water(weights, current, seed_shift) for current in WATERS)


def main() -> int:
    rng = np.random.default_rng(7)
    shape = (6, len(FEATURES))
    # Start from the hand-written hold's own gains, roughly: that is a fair
    # starting point, and what learning has to beat.
    mean = LinearHold.seed_weights()
    spread = np.full(shape, 8.0)
    began = time.time()
    best_score, best = -1.0, mean.copy()
    for generation in range(GENERATIONS):
        samples = [mean + spread * rng.standard_normal(shape) for _ in range(POPULATION)]
        scores = np.array([rollout(w, 0.0) for w in samples])
        order = np.argsort(-scores)
        elite = np.stack([samples[i] for i in order[:ELITE]])
        mean = elite.mean(axis=0)
        spread = elite.std(axis=0) + 0.5
        if scores[order[0]] > best_score:
            best_score, best = float(scores[order[0]]), samples[order[0]].copy()
        print(f"generation {generation + 1:2d}: best {scores[order[0]]:.3f}  mean {scores.mean():.3f}  "
              f"({time.time() - began:.0f} s)", flush=True)

    final = rollout(mean, 0.0)
    chosen = mean if final >= best_score - 0.02 else best
    from hold import StationHold

    # Every water, both controllers, because one water is how the last one came to
    # be reported as better than the hand-written hold when it was better in one
    # place and worse in three.
    print(f"learned: {max(final, best_score):.3f} across all of them, by its worst. "
          "Water by water, against the hand-written hold:")
    print(f"  {'water':>16}  {'learned':>9}  {'hand-written':>13}")
    for current in WATERS:
        theirs = Tank("bluerov2", seconds=SECONDS,
                      task=hold_station(seconds=SECONDS, radius_m=0.5, depth_band_m=0.3),
                      sensed=True, current=current,
                      latency_ticks=LATENCY_TICKS).run(StationHold())
        ours = Tank("bluerov2", seconds=SECONDS,
                    task=hold_station(seconds=SECONDS, radius_m=0.5, depth_band_m=0.3),
                    sensed=True, current=current,
                    latency_ticks=LATENCY_TICKS).run(LinearHold.with_weights(chosen))
        said = f"{current[0]:.2f} m/s @{current[1]:.0f}"
        print(f"  {said:>16}  {ours.score:9.3f}  {theirs.score:13.3f}")

    # Written out as a controller of its own, weights and all, so that the file
    # is the thing that is deployed: no model to fetch, nothing to look up.
    source = (HERE / "hold_policy.py").read_text()
    baked = source.replace("WEIGHTS: list[list[float]] | None = None",
                           "WEIGHTS: list[list[float]] | None = " + json.dumps([[round(float(v), 5) for v in row] for row in chosen]))
    (HERE / "learned_hold.py").write_text(baked)
    print("wrote", HERE / "learned_hold.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
