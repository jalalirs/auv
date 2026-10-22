#!/usr/bin/env bash
# Deploys commit 3b3004982e4d to the box: MCP dives a place in its newest
# published version (a draft laid on Al Fahal had every MCP dive there
# refused), and a pipeline's burial is a share of its diameter, 0 to 1,
# everywhere. Run on the box:
#   bash ~/iocean/scratch/deploy-3b3004982e4d/deployments/box/deploy-3b30049.sh
# Before it: this commit exported there and its control-plane and mcp images
# built. No migration, no new env. Safe to run twice.
set -euo pipefail
SHA=3b3004982e4d
D=~/iocean/scratch/deploy-$SHA/deployments/box
cd "$D"
cp ~/code/auv/deployments/box/.env .env
docker compose --env-file .env up -d --no-deps control-plane mcp
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
