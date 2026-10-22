#!/usr/bin/env bash
# Deploys commit e8732a4f7641 to the box: a reconstruction can carry the
# vehicle's own navigation (camera positions and lens) instead of solving the
# cameras from murky frames, and can say it is a structure; the reconstruction
# image r4 does it. Run on the box:
#   bash ~/iocean/scratch/deploy-e8732a4f7641/deployments/box/deploy-e8732a4.sh
# Before it: this commit exported there, its control-plane and mcp images
# built, and iocean/reconstruct-video:r4 built. No new migration. Safe to run
# twice.
set -euo pipefail
SHA=e8732a4f7641
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. migrations (none new; safe to run)"
cp "$ENV" .env
docker compose --env-file .env run --rm migrate

echo "2. the reconstruction image r4, by its content identity"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r4)
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
