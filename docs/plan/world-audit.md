# Audit of the six places (2026-11-03)

Step 2 of `worlds-2026-11.md`. For each of the organisation's six places:
what it was built from, where those foundations are now, what must be
fetched again, and the layers it becomes under `world-document.md`.
Read from each place's newest version, its builds and the box.

## What holds for all six

- **No public foundation is a platform asset.** GEBCO, Sentinel-2, ICESat-2,
  the Allen Coral Atlas, GMRT and the depth model's output were fetched at
  build time, used and thrown away. What survives is on the box's disk
  only: `~/coral-city/reference/<place>` (Al Fahal's 158 MB, and the store
  places), `~/iocean/source/icesat` (67 GB of ATL24 granules, shared),
  `~/iocean/source/rsde` (a Red Sea 5 m depth grid). The recipes say
  exactly how to fetch the rest again.
- **A place can lose its parts.** Al Fahal with the Red Sea reef uses a
  video reef that was archived on 2026-11-02. Archiving an asset a world
  uses must at least warn.
- **Water is chosen, never measured.** Every Red Sea place says Jerlov IB
  "chosen by region" (Overmans & Agusti 2020). Fine as the world's water
  parameters.
- **Life is in one place only** (the Jeddah tank). The store Al Fahal has a
  species list; the copy built on it dropped it.

## The six

### 1. Al Fahal with the Red Sea reef
`city_01M5VHA276DB6QMQ174B4B9XVB`, v2, 2.9 GB, 3 km square at 22.284, 38.962.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | the store Al Fahal v36 (`ver_01M4QSXQ05FG087R148EJDEFWY`, published), whose depth is the learned model `unet-v2-redsea-w10` on Sentinel-2, fitted to 37,742 ICESat-2 photons (rms 0.79 m), GEBCO around it | v36 published; its inputs on box disk in `~/coral-city/reference/al-fahal` (learned depth .npz, ICESat points, atlas geojson, seabed grids); built by the older tools, so no recipe |
| reef, cover | Allen Coral Atlas benthic and geomorphic, Red Sea assemblage, 1,039,632 colonies | atlas geojson on disk; colonies are derived and can be made again |
| reef, video | "Red Sea reef (MCP test)" `recon_01M5HCXB4WB4WAKM11F7T8TAFX`, scale assumed (1 COLMAP unit = 7.58 m) | **archived 2026-11-02**; its video (2.1 GB) still in storage |
| water | IB, chosen by region | |
| life | none in this copy | the store Al Fahal's `fauna.json` on box disk |

To fetch again: nothing. To import as assets: the learned depth, the ICESat
points, the atlas, the GEBCO surroundings. Decide: unarchive the video reef
or drop it.

### 2. Jeddah airport tank
`city_01M4106850Y74RGD3A5BSQ44GX`, v7, 32 MB. Not in the organisation (no org), discoverable.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | `tools/make-jeddah-tank` seed 11: sand, boulders, the column with its ledges, read off two phone videos and published facts (14 m tall, 10 m across) | the tool is in the repo; the two videos not found in the platform |
| structures | the round glass wall (5 m radius), which stops a vehicle | written as `enclosed` in site.json, not as an object |
| reef | 114 colonies placed on the ledges, chosen | in the package |
| water | type I, chosen (filtered aquarium water) | |
| life | 11 species with counts, read off the footage | in site.json |

A virtual world: no georeference. Nothing to fetch. The glass becomes a
structure; the life list becomes the first species asset. Move it into the
organisation.

### 3. SubPipe outfall pipeline
`city_01M60Z55CB6JJV87ZKXGKHA4DW`, v2, 169 MB, 300 m square.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | a flat seabed at 17 m, assumed | a parameter, nothing to keep |
| structures | "SubPipe outfall pipeline, run 3, colour evened" `recon_01M5T8G5MZ8SMDGV4VGQGT24Z4` (video, Oceanscan-MST, CC BY 4.0) | live |
| water | IB, chosen as Red Sea | |

The georeference (22.3, 38.85) is invented: the footage is from Portugal.
It should be a virtual world with no georeference, and its water should not
claim the Red Sea. Seven builds of this place exist (four named "SubPipe
outfall pipeline"), and two older reconstructions of the same run
(`recon_01M5J9YW…` archived, `recon_01M5JEK8…` live): tidy.

### 4. Thuwal Deep
`city_01M2DM5ACX3PXXH0ERQ9BJN08C`, v2. No organisation, not discoverable.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | GMRT, 8 km at 15.66 m, 519 to 638 m deep; GEBCO 15" surroundings (49 x 49) | the built grids in the package and in `~/iocean/places/thuwal-deep`; GMRT itself not kept |
| reef, water, life | none | |

To fetch again: GMRT for the square (`iocean_places/fetch/bathymetry.py`
does it). The package carries macOS `._*` junk files. Move it into the
organisation.

### 5. Thuwal export line (open water)
`city_01M5VJ84TZWC30M4ZGX11J0TZ6`, v2, 206 MB, 600 m square at 22.305, 38.955.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | recipe: Sentinel-2 (Stumpf ratio and a median image), learned depth `unet-v2-final`, ICESat-2 (9 photons, 1 pass), GEBCO; fitted by curve and colour models | recipe in the package; the model is in `iocean-places:r6`; the fetched sources were not kept |
| reef, cover | Allen Coral Atlas, Red Sea assemblage, 16,658 colonies | derived |
| structures | the export line, a route drawn on the map, `recon_01M5VHAFSZ4VTZY2HS7JJGKEKV`, 406 m, 0.8 m pipe, a quarter buried | live |
| water | IB, chosen by region | |

To fetch again: the Sentinel-2 scenes, GEBCO tile, atlas; ICESat is on
disk. The recipe is the terrain stack as it stands. An earlier build,
"Thuwal export line" (`bld_01M5VHA3H3…`), has no version.

### 6. Thuwal reef calibrated
`city_01M4MN3MPJF84NP5H9GAQZM0BD`, v1 only, **never published**, 1 km square at 22.255, 38.958.

| Layer | Built from | Where it is now |
|---|---|---|
| terrain | recipe: Sentinel-2 Stumpf and median, ICESat-2 (16 photons, 4 passes), GEBCO, Allen Coral Atlas; curve and colour models | recipe and heights.json in the version; sources not kept |
| reef, water, life | none | |

It lies inside Al Fahal's 3 km square, so it is a smaller, terrain-only
duplicate of the same reef. Proposal: fold it into Al Fahal as a second
terrain candidate, or archive it.

## What this asks of the platform

1. Public sources become assets when fetched: a depth grid, an image, a
   point set, a cover map, each with citation and licence, cut to a square.
   Builds read assets instead of fetching and forgetting.
2. Import Al Fahal's reference folder as such assets first: it is the
   richest and is already on disk.
3. A species list asset (from the tank's counts and Al Fahal's fauna).
4. Archiving an asset a world uses warns and names the worlds.
5. Tidy: SubPipe's seven builds and duplicate reconstructions, Thuwal Deep's
   `._*` files, the two places with no organisation.

## The six as worlds

| World | Georeference | Terrain | Reef | Structures | Life |
|---|---|---|---|---|---|
| Al Fahal | yes | learned depth + ICESat + GEBCO (import) | atlas cover; video reef (decide) | | Al Fahal species |
| Jeddah airport tank | none | the tank, authored | 114 colonies | glass wall | 11 species |
| SubPipe outfall | none (was invented) | flat 17 m | | the pipeline from video | |
| Thuwal Deep | yes | GMRT + GEBCO (fetch GMRT) | | | |
| Thuwal export line | yes | the recipe's five sources (fetch) | atlas cover | export line route | |
| Thuwal reef calibrated | yes | fold into Al Fahal or archive | | | |
