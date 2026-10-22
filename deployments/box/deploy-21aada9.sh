#!/usr/bin/env bash
# Deploys commit 21aada90c867 to the box: a reconstruction can say it is a
# structure (a pipeline an AUV followed, say); it is made, searched for and
# laid as a reef is, and kept as a structure. Run on the box:
#   bash ~/iocean/scratch/deploy-21aada90c867/deployments/box/deploy-21aada9.sh
# Before it: this commit exported there and its control-plane and mcp images
# built. No migration, no new env. Safe to run twice.
set -euo pipefail
SHA=21aada90c867
D=~/iocean/scratch/deploy-$SHA/deployments/box
cd "$D"
cp ~/code/auv/deployments/box/.env .env
docker compose --env-file .env up -d --no-deps control-plane mcp
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
