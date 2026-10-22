#!/usr/bin/env bash
# Deploys commit e019f0714e96 to the box: assets of every kind (a seabed
# survey, a structure from a 3D model, a pipeline from its route), and the
# reconstruction image that lays several assets in one job (r3; r2 could not
# read the several-reefs brief 76a54cd sends). Run on the box:
#   bash ~/iocean/scratch/deploy-e019f0714e96/deployments/box/deploy-e019f07.sh
# Before it: this commit exported there, its control-plane and mcp images
# built, iocean/reconstruct-video:r3 built, and the database backed up to
# ~/iocean/backups/coral-before-e019f0714e96.dump. Safe to run twice.
set -euo pipefail
SHA=e019f0714e96
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. migration 0040 (an asset is a reef, a structure or a survey)"
cp "$ENV" .env
docker compose --env-file .env run --rm migrate

echo "2. the reconstruction image r3, by its content identity"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r3)
[ -n "$RECON" ]
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env

echo "3. the control plane and MCP"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "4. checks"
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
