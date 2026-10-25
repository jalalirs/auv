#!/usr/bin/env bash
# Deploys commit 8fec79ea5ca3 to the box: places can be retired and brought
# back (hidden from lists, new dives refused, history kept). Run on the box:
#   bash ~/iocean/scratch/deploy-8fec79ea5ca3/deployments/box/deploy-8fec79e.sh
# Before it: this commit exported there, its control-plane and mcp images
# built, and the database backed up to
# ~/iocean/backups/coral-before-8fec79ea5ca3.dump. Migration 0041; no new env.
# A dive already running carries on. Safe to run twice.
set -euo pipefail
SHA=8fec79ea5ca3
D=~/iocean/scratch/deploy-$SHA/deployments/box
cd "$D"
cp ~/code/auv/deployments/box/.env .env

echo "1. migration 0041 (a place can be retired and brought back)"
docker compose --env-file .env run --rm migrate

echo "2. the control plane and MCP"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "3. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
