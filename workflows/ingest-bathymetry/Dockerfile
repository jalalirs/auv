# syntax=docker/dockerfile:1.17
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS base

# Reading a netCDF grid and rendering it needs these three and nothing else.
RUN pip install --no-cache-dir \
      "numpy==2.2.6" \
      "netCDF4==1.7.2" \
      "pillow==11.3.0"

WORKDIR /work
COPY workflows/ingest-bathymetry/ingest.py /usr/local/bin/ingest.py

# The container runs with a read-only root and no capabilities. It writes only
# to the outputs directory the worker binds for it.
ENTRYPOINT ["python", "/usr/local/bin/ingest.py"]
