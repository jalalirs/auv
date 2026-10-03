# What the vehicle did to the reef, and what it missed: Looe Key, 3 October 2026

```
tools/count-bias --place looe-key --vehicles mini-hoot,boxfish-luna --seeds 0,…,10 --altitude 1.5|0.6
```

(The seeds were split across parallel processes and merged with `--merge`.)

The report pages are in `count-bias-looe-key-2026-10-03/at-1.5m/` and `at-0.6m/`:

- `compare.html`
- one page per vehicle, every figure tagged with what it is and where it came from
- `count-bias.json`

This replaces the 2 October result. Those transects were flown as `reach` objectives, and a reach ignores altitude, so they ran at the dive's starting depth. These are `transect` objectives, which hold their height over the bottom. They were flown at the asked height for 88–99% of each line (mean 93–94%).

## How far the vehicle biased its own count

| height | mini-hoot (2.7 kg) | Boxfish Luna (25 kg) | mini-hoot − Luna, paired |
|---|---|---|---|
| 1.5 m | **81%** (68–89%), 255 of 315 | **78%** (55–94%), 265 of 338 | +3 pts (−8 to +16) |
| 0.6 m | **95%** (75–111%), 258 of 271 | **81%** (58–95%), 269 of 331 | +14 pts (0 to +33) |

**How the share was computed.** It is the number of fish the camera counted divided by the number counted on the same dive with fish blind to the vehicle.

**Intervals.** All intervals are 95% bootstrap intervals over the 11 seeds.

**Reading it.**
- **At 1.5 m:** the two vehicles cannot be told apart.
- **At 0.6 m:** the small vehicle counts more of what was there than Luna does. The paired interval only just reaches zero, so this is suggestive, not settled.
- **Why mini-hoot's share is higher at 0.6 m than at 1.5 m:** each height's share is measured against its own blind twin. Closer to the reef, the camera sees fewer fish either way.

## What it did to the reef (summed over 11 transects)

| | mini-hoot 1.5 m | Luna 1.5 m | mini-hoot 0.6 m | Luna 0.6 m |
|---|---|---|---|---|
| fish put to flight by the vehicle | 269 | 337 | 275 | 385 |
| fish it ran into | 1 | 3 | 3 | 10 |
| colonies struck | 1 | 5 | 10 | 31 |
| colonies that shut their polyps | 1 | 17 | 10 | 292 |
| colonies smothered | 0 | 0 | 0 | 1 |
| sand lifted, g | 0 | 0 | 0 | 3.1 |
| most sediment settled on one colony, mg/cm² | — | — | — | 0.48 |
| ground contacts | 0 | 0 | 0 | 0 |

No colony was broken or torn off. Visibility in front of the camera never fell below 32 m.

**Each transect.** Each was 1,272 fish and 83,055 colonies.

**Where the difference is.** It is in the wash, not the count:
- Flown low, Luna's thrusters shut the polyps of 18–43 colonies a transect, against mini-hoot's 0–3.
- Luna also lifts sand.

**Where each figure comes from.** Every figure is derived, not measured. Its page says from what:
- **fish put to flight:** Hein's looming rule;
- **sand:** the Shields threshold, with an assumed erodibility;
- **polyps:** an assumed 8 cm/s wash threshold;
- **smothering:** Erftemeijer's 10 mg/cm² a day.
