# Reefs4D ingestion

This pipeline creates an interactive visual OpenUSD derivative while preserving
the immutable scientific source outside Git. It uses texture-aware quadric
decimation and writes OpenUSD 25.11, matching Isaac Sim 6.0.

The first pinned input is `reefs4d.c2.2019`. Run it from the Mac with:

```bash
./tools/reef-data fetch
./tools/reef-data prepare
./tools/reef-data validate
./tools/reef-data status
```

Raw and derived assets live below `${AUV_DATA_DIR}/red-sea-twin` on the GPU
host (by default `/home/jalalirs/code/auv-data/red-sea-twin`). The committed
source manifest is the authority for URLs, checksums, rights, coordinate
uncertainty, and scientific limitations.
