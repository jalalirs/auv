# Box audit for production, 2026-10-31

Read-only. Nothing was removed.

## Disk

Root disk 1.9 TB, 86% used, 250 GB free.

| What | Size | Whose |
|---|---|---|
| ~/iocean (= ~/coral-city) | 571 GB | ours |
| Docker images, all projects | 275 GB (160 reclaimable) | shared |
| Docker volumes, all projects | 296 GB | mostly others (drai 90, reader 47, itraffic 46, zameel 46, areen 24); ours: coral-city_registry 14 GB, coral-city_record 0.3 GB |
| Docker build cache, default builder | 59 GB per `docker system df`, 149 GB per `buildx du` | shared by every project built on the box |
| ~/code | 150 GB | drai 138 GB; auv checkout small |

Inside ~/iocean: storage 163, ml 143, work 130, source 67 (icesat), reference 37, attic 15, scratch 6, probe 5.5, places 4.5, deliverables 2.

## Ours that could go (needs approval)

- **work/run_\***: 1,849 run folders since 2026-08-30, 117 GB. Only 329 have a row in `dive.run`; the other 1,520 belong to no run the platform knows. 1,833 are older than 14 days.
- **attic**: 15 GB of `al-fahal.before-*` and `kaneohe.before-*` snapshots from 2026-10-09/10.
- **Stopped one-off containers**: iocean-vs, iocean-fuse*, iocean-recon-*, iocean-lay-test (small).
- **Images**: old reconstruct-video r2 to r9 and sim-runtime r1 to r3 share layers, so they free little (under 0.6 GB each). deepreefmap:dev holds 7.7 GB of its own. These belong to the auv session's work; ask it first.
- **ml runs**: 143 GB, biggest deepreefmap/single-whole-held 21 GB. The auv session's; ask it.

Not ours: the build cache and other projects' volumes. The build cache is the user's call.

## Removal proposal (measured 2026-10-31)

1. **1,520 orphan run folders, 102 GB.** Dated 2026-08-30 to 2026-09-19, none newer. No row in `dive.run`, so no screen, MCP tool or bench can reach them (bench reads artefacts through the API, not the folder). Owned by root and the container uid, so they go through the helper container, one validated `run_<ULID>` name at a time, re-checked against the record at removal. The 329 known runs (15 GB) and `work/objects` stay.
2. **attic, 15 GB.** 50 `before-*` copies of al-fahal, kaneohe and the three coral libraries, 2026-09-14 to 2026-10-12. Every place has been rebuilt and published since. Owned by us.
3. **Stopped one-off containers:** iocean-vs, iocean-fuse, iocean-fuse-kaust, iocean-fuse-synth, iocean-recon-kaust, iocean-recon-squid, iocean-recon-synth, iocean-lay-test. Kilobytes; removes clutter only, images stay. Not touched: iocean-keep-*, iocean-bootstrap-1, iocean-migrate-1.

Total about 117 GB, which takes the disk from 86% to about 80% used.

**Done 2026-10-31:** all three removed. 329 runs left, attic empty, disk 80% used, 366 GB free.

## Production gaps

- **No backup of iOcean.** Cron backs up reader and areen nightly; nothing copies the iOcean record (Postgres) or storage (MinIO, 163 GB).
- **No health watch.** The control plane has /health/live and /health/ready, but the edge does not route them (404 at :18084/api/health/ready) and nothing checks them.
- **Prod and test share one deployment.** Scratch dives and edge checks (iocean-edge-check-d) run next to the live services, and test places sit in the same record and storage as published ones.
- **Reachable only over Tailscale** (edge bound to 100.76.65.1). The box was unreachable 2026-10-28 to 31.
- Record holds 6 catalogue versions, 3 cities, 329 runs.
