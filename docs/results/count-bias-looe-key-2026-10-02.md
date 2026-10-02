# How much the vehicle's presence cost its fish count: Looe Key, 2 October 2026

`tools/count-bias --place looe-key --vehicles mini-hoot,boxfish-luna --seeds 0,1,2,3`

| vehicle | counted, fish see it / fish blind to it | share of what was there |
|---|---|---|
| mini-hoot (2.7 kg, 0.34 m) | 180 / 236 over 4 seeds | **76%** |
| Boxfish Luna (25 kg, 0.73 m) | 165 / 238 over 4 seeds | **69%** |

**How it was measured.** Both vehicles fly the same transects on the same seeds:

- from where the dive begins, through the nearest school of fish, 10 m past it;
- 1.5 m off the bottom;
- untethered.

Each transect is flown twice: once with fish that see the vehicle, and once with fish that are blind to it (`CORAL_CITY_FISH_BLIND`). The second run is what was there to be counted.

The camera counts each fish once. A fish counts when it is in the field of view and within half the visibility, at most 5 m (systems/fish.py).

Fish flee by Hein et al.'s looming rule. Its threshold is set so that a vehicle closing at 0.15 m/s half-frightens a fish at its species' flight distance; a vehicle working harder is seen from further.

**What it says.** The vehicle's own presence cost the count a quarter to a third of the fish that were there. The larger, harder-working vehicle cost more.

That is the order of what the literature measures:

- Laidig 2013: 57% of fish reacted to an ROV.
- Lindfield 2014: a silent diver counts up to 2.6 times more fish at fished sites.

**What it does not say.**

- **Seeds vary widely.** Single runs go from 37% to 105%: fish fleeing into the frame are counted too. Four seeds is a first look, not a number to quote.
- **The rule's numbers are chosen, not fitted to wild data.** Hein's measurements are for divers, not vehicles.
- **Lights and noise are left out.** Luna's 20,000 lumens are not part of what fish react to, and Benoit-Bird 2023 found that lights change reactions a great deal.

Raw rows are in `count-bias-looe-key-2026-10-02.jsonl.txt`.
