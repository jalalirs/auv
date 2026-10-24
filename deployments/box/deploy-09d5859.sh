#!/usr/bin/env bash
# Deploys commit 09d58591bf99 to the box: the reconstruction image r5. Laid
# structures get a surface by type and the pipe faces outward; a laid splat
# strip's edge fades with its width and the place's ground takes its sand
# colour around it. Run on the box:
#   bash ~/iocean/scratch/deploy-09d58591bf99/deployments/box/deploy-09d5859.sh
# Before it: iocean/reconstruct-video:r5 built. No migration; only the control
# plane restarts, to read the new image. Safe to run twice.
set -euo pipefail
SHA=09d58591bf99
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r5)
[ -n "$RECON" ]
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
