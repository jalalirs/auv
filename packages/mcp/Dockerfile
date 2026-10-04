# iocean over MCP, for agents that are not on this machine.
#
# No Python dependencies — the server speaks the protocol and HTTP with the
# standard library — and one system one: ffmpeg, because dives_frame reads a
# moment out of a dive's own video and nothing short of a decoder can.
#
# It holds no credential. Each agent sends its own, and it is forwarded to the
# platform untouched.

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY packages/mcp/coral_city_mcp /srv/coral_city_mcp

# The app's doubt catalogue is read by a test, not by the server; nothing else
# from the repository belongs in here.
RUN useradd --uid 1234 --no-create-home mcp
USER mcp

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

ENTRYPOINT ["python", "-m", "coral_city_mcp", "--http", "0.0.0.0:8080"]
