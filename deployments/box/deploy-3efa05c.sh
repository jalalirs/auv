#!/usr/bin/env bash
# Deploys commit 3efa05c2d035 to the box: the reconstruction image r7. With
# enhance, the colour's drift along a run is taken out of the frames before
# training (SubPipe ran blue at its ends and green in the middle). Run on the box:
#   bash ~/iocean/scratch/deploy-3efa05c2d035/deployments/box/deploy-3efa05c.sh
# No migration; only the control plane restarts. Safe to run twice.
set -euo pipefail
SHA=3efa05c2d035
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r7)
[ -n "$RECON" ]
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
