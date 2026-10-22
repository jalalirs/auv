#!/usr/bin/env bash
# Deploys commit 76a54cd14794 to the box: several reefs laid into one place in
# one mapping (a search and a choice each, one lay), and MCP's mappings tools
# for it. Run on the box:
#   bash ~/iocean/scratch/deploy-76a54cd14794/deployments/box/deploy-76a54cd.sh
# Before it: this commit exported to ~/iocean/scratch/deploy-76a54cd14794, its
# control-plane and mcp images built (not started), and the database backed up
# to ~/iocean/backups/coral-before-76a54cd14794.dump. No new env. Safe to run
# twice.
set -euo pipefail
SHA=76a54cd14794
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"
cp "$ENV" .env

echo "1. migration 0039 (a mapping holds several assets)"
docker compose --env-file .env run --rm migrate

echo "2. the control plane and MCP"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "3. checks"
sleep 8
BIND=$(sed -n 's/^IOCEAN_BIND_ADDRESS=//p' "$ENV"); BIND=${BIND:-127.0.0.1}
curl -fsS "http://$BIND:18080/api/v1/platform" | head -c 300; echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
