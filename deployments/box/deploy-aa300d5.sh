#!/usr/bin/env bash
# Deploys commit aa300d5bbef9 to the box: MCP's uploads_start and
# uploads_confirm, so an agent can put a dive video in storage. Run on the box:
#   bash ~/iocean/scratch/deploy-aa300d5bbef9/deployments/box/deploy-aa300d5.sh
# Before it: this commit exported there and its mcp image built. No migration,
# no new env; only MCP restarts. Safe to run twice.
set -euo pipefail
SHA=aa300d5bbef9
D=~/iocean/scratch/deploy-$SHA/deployments/box
cd "$D"
cp ~/code/auv/deployments/box/.env .env
docker compose --env-file .env up -d --no-deps mcp
sleep 6
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|mcp)'
echo "deployed $SHA"
