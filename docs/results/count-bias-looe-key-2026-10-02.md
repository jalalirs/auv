# How much the vehicle's presence cost its fish count: Looe Key, 2 October 2026

`tools/count-bias --place looe-key --vehicles mini-hoot,boxfish-luna --seeds 0,1,2,3`, then `--seeds 4,…,11`

| vehicle | counted, fish see it / fish blind to it | share of what was there | 95% interval |
|---|---|---|---|
| mini-hoot (2.7 kg, 0.34 m) | 389 / 498 over 11 seeds | **78%** | 66–90% |
| Boxfish Luna (25 kg, 0.73 m) | 423 / 592 over 11 seeds | **71%** | 61–84% |

Seed 11's transect passed no fish for either vehicle and is left out. The intervals are bootstrapped over seeds (5,000 resamples). The first four seeds alone gave 76% and 69%.

Neither vehicle touched anything on any transect: no fish struck, no ground, no coral, no sand lifted, visibility never below 32 m (seeds 4–11; the first four were flown before this was recorded). At 1.5 m off the bottom, what a vehicle does to the count is its presence, not its wash.

**How it was measured.** Both vehicles fly the same transects on the same seeds:

- from where the dive begins, through the nearest school of fish, 10 m past it;
- 1.5 m off the bottom;
- untethered.

Each transect is flown twice: once with fish that see the vehicle, and once with fish that are blind to it (`CORAL_CITY_FISH_BLIND`). The second run is what was there to be counted.

The camera counts each fish once. A fish counts when it is in the field of view and within half the visibility, at most 5 m (systems/fish.py).

Fish flee by Hein et al.'s looming rule. Its threshold is set so that a vehicle closing at 0.15 m/s half-frightens a fish at its species' flight distance; a vehicle working harder is seen from further.

**What it says.** The vehicle's own presence cost the count a fifth to a third of the fish that were there.

Whether the larger, harder-working vehicle costs more is **not settled**. Over four seeds it looked so. Over eleven, paired seed by seed, mini-hoot counts 6.7 points more of what was there than Luna, but the 95% interval on that difference runs from −9 to +21 points. It is the likelier way round (81% of resamples), and no more than that.

That is the order of what the literature measures:

- Laidig 2013: 57% of fish reacted to an ROV.
- Lindfield 2014: a silent diver counts up to 2.6 times more fish at fished sites.

**What it does not say.**

- **Seeds vary widely.** Single runs go from 25% to 105%: fish fleeing into the frame are counted too. Eleven seeds gives the interval above; telling the two vehicles apart would take several times more.
- **The rule's numbers are chosen, not fitted to wild data.** Hein's measurements are for divers, not vehicles.
- **Lights and noise are left out.** Luna's 20,000 lumens are not part of what fish react to, and Benoit-Bird 2023 found that lights change reactions a great deal.

Raw rows are in `count-bias-looe-key-2026-10-02.jsonl.txt`.
