# Shushah place — build notes (26 Sep 2026, parallel session; nothing in the repo touched)

Centre 27.9366 N 34.9108 E (Abu Shusha island, ~16 km off Sharma; OSM name lookup),
2000 m across. Reference: ~/coral-city/reference/shushah. Place: ~/coral-city/places/shushah.

## Sources
- Sentinel-2 S2B_T36RXR_20251110 (0.0% cloud), Stumpf ratio, uncalibrated: 67% bottom visible, 3.91 m samples.
- Allen Coral Atlas: maps 0.62 km2 of the 4 km2 box; Rubble 36.5 / Rock 32.3 / Coral-Algae 20.0 / Sand 11.1 % of mapped.
- RSDE 2022 multibeam (Zenodo 19065211, CC BY 4.0): L4D 5 m grid downloaded (230 MB) — NO soundings within 12 km of Shushah. Not usable here.
- Water IA: Kd(PAR) 0.039/m off Duba, Overmans & Agusti 2019 (doi 10.1111/php.13112).
- Cover/assemblage literature for the calibrated rebuild: Lin et al. 2023 Mar Pollut Bull (NE Red Sea: 32% stony coral, 4% soft, doi 10.1016/j.marpolbul.2023.115693); Pisapia, Osman & Johnson 2026 Mar Pollut Bull (northern sites 42.6% higher cover than central; Porites/Pocillopora/Acropora; doi 10.1016/j.marpolbul.2025.119050).

## Things found in the tools (for the r4 session — not fixed here)
1. tools/get-reef `clearest_scene` sorts by cloud only. Both 2024-09-01 scenes (T36RXS, T36RXR) are nodata edge to edge over Shushah but 0% cloud, so they win and get-reef exits "open water". Scratchpad wrapper get-reef-covered.py probes a coarse green band and skips scenes <95% valid. Worth folding in.
2. read_band applies scale+offset to nodata zeros -> -0.1 reflectance; nothing masks it.
3. tools/coral-atlas --into X writes X/<name>/ (creates the subdir); get-reef --into writes flat. Easy to end up with reference/shushah/shushah/.

## State of the first build (uncalibrated)
75% underwater (island 25%). 47.7% of the site sits at 15–22 m = the Stumpf saturation floor (same fault Al Fahal had at 29%). asked cover 0.40, paid 0.22 where it grows over 3.7 km2 — grown over the floor. Needs icesat -> fit-depths -> past-the-limit -> rebuild.

## Calibration (ICESat-2 ATL24: 31 passes, 16 with seafloor, 7,206 photons, median sigma 0.17 m)
fit-depths: measured = 0.505 x claimed - 4.89; rms 6.84 -> 4.49 m (Al Fahal was 2.0). Binned truth:
- claimed 14-23 m  -> measured ~14 m (a flat terrace at 13-15 m all round the island; Stumpf 3-6 m too deep there)
- claimed 0.5-3 m  -> measured 0.6-1 m on the reef flat, but the affine fit puts the flat at ~5.8 m. WRONG on the flat, i.e. exactly where the restoration grid is.
- 241 photons at 2-10 m fall on cells get-reef called LAND (nir > 0.03): bright sandy shallows read as island. Island footprint (25%) is overstated.
- fit-depths applied the fit to land too -> island 4.6 m underwater. Patched in reference/shushah/seabed_fitted.f32 (land cells restored to +0.6 m), recorded as "landRestored" in seabed_fitted.json.
No sensor-floor clamp survives the fit (0.2% at the deepest), so past-the-limit is not applicable. GMRT 20 km: the island sits on a platform 8 m (1-1.5 km) / 17 m (1.5-2.5 km); deep water N and W is ~20 m, S and E 60+ m.

4. For the r4 session: fit-depths' single affine fit does not hold where there are two regimes (1 m flat, 14 m terrace). A two-segment or offset-only fit, or fitting only where claimed < optical limit, would put the flat right. get-reef's NIR land test needs a depth guard.

## The real finding on Shushah's depths (after the calibrated rebuild)
Cells the satellite claims at 0.5-3 m are BIMODAL against the laser: p25 0.6 m (the reef flat) and p75 14.7 m (bright sand on the 14 m terrace). Stumpf's single ratio is not a function of depth here because the bottom type changes — the pale terrace sand returns as much green as the shallow flat. No affine or lookup calibration can separate them; only a second source can. Consequence in the built place: shallowest 4.89 m, no reef flat at all (real flat 0.5-1 m by 1,329 photons), the start point chosen at 14 m with "87% cover".
=> Shushah cannot be made right from public data. It needs KCRI's own multibeam / photogrammetry (Ocean Aero AUSV bathymetry + HD video twin exists), which is the ask to make of them. The place as built is honest in its record (surveyed: false, rms 4.49 m) and wrong on the flat; say so on any slide.

5. tools/ground rasterises reference/habitat.geojson (survey polygons) into habitat_4096.npy and OVERWRITES the Atlas one tools/coral-atlas wrote. On a place with no survey polygons (habitat.geojson = empty FeatureCollection) the result is all zeros, and flyover.py then has no cells to hang its flight on (IndexError at vt[0]). ground should keep an existing habitat_4096.npy when it has no polygons of its own.

## Rendering (26 Sep, evening)
- Isaac tour washed out at IA and at IB alike. Cause is not the water: the runtime rendered "water_is 1C" both times (site.json's water type is not what the tour renders — as r3 already says, everything is 1C). Cause is the meter: the tour's frame 0 looks down from above on the island (floorAtMiddleM 0.6), reads dark, and `metered` raised ISO 268.9 -> 12000 "out of rounds", then held it for 720 frames over 5-14 m bright sand. 6. For r4: a tour over a place whose middle is land meters on the land; meter on the anchor instead, or cap the meter at a few stops from the depth value.
- Worked around with CORAL_CITY_ISO=269 via a scratchpad copy of tools/fly-over (~/coral-city/fly-over-pinned on the box). Not a repo change.
- Second rebuild used --ground with tools/ground's colour_4096.png present, so make-site recorded ground.surveyed=true, colourFrom "orthomosaic from a survey". 7. make-site should not call a satellite-derived colour_4096.png a survey orthomosaic.

## 27 September 2026 — after the box was rebuilt

The teaser at `renders/teaser-2026-09-26.mp4` is the first cut: title cards,
9.5 s of Blender terrain, 11 s of Isaac dive view. It was rejected for the
cards and for the resolution.

The replacement is one continuous 1920x1080 descending orbit of the island,
576 frames at 64 samples, no text of any kind — rendered from
`flyover_orbit.py`, a variant of `tools/flyover.py` whose `pose()` is a single
clockwise orbit from the north-east at 780 m out and 420 m up to the
south-west at 560 m and 150 m, looking at the eastern reef flank throughout.
The stock `pose()` could not be used: it hangs its flight off the surveyed
band or the spur-and-groove polygons, and Shushah has neither, so the middle
of its flight crossed blank terrace.

Two things that had to be true first, both consequences of the home directory
being lost: Blender was reinstalled at `~/tools/blender-4.5.3-linux-x64`, and
`reference/shushah` was copied back from the laptop, which is the only place
the 1 m ground, the habitat raster and `chart_4096.png` still existed.
