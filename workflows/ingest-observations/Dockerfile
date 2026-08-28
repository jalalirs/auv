# syntax=docker/dockerfile:1.17
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

# Nothing is installed. Reading a text feed needs the standard library and
# nothing beyond it, and every dependency not taken is one that cannot break
# the heartbeat.

WORKDIR /work
COPY workflows/ingest-observations/ingest.py /usr/local/bin/ingest.py

ENTRYPOINT ["python", "/usr/local/bin/ingest.py"]
