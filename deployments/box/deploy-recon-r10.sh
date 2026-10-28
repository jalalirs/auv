#!/usr/bin/env bash
# Deploys commit 0afc30ae06a4 (the control plane refuses an objective with no
# judge) and reconstruction image r10: r9 with ml/splat/trim_splats.py from
# 0b767277cc5d (a strip's faded edge takes its median ground colour, so it is
# not a dark band). Run on the box:
#   bash ~/iocean/scratch/recon-r10/deploy-recon-r10.sh
# Both images are already built. No migration; only the control plane restarts.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-0afc30ae06a4/deployments/box
[ -f ~/iocean/backups/env-before-recon-r10 ] || cp "$ENV" ~/iocean/backups/env-before-recon-r10
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r10)
[ -n "$RECON" ]
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "control plane 0afc30a and reconstruct r10 are live"
