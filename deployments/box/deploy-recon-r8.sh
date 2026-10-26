#!/usr/bin/env bash
# Deploys reconstruction image r8: r7 with lay.py from 4b1c3d6 and the commit
# after it. A vehicle's strip fades over its outer 2 m at lay, not the trimmed
# 1 m. Run on the box:
#   bash ~/iocean/scratch/recon-r8/deploy-recon-r8.sh
# No migration; only the control plane restarts. Safe to run twice.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box
[ -f ~/iocean/backups/env-before-recon-r8 ] || cp "$ENV" ~/iocean/backups/env-before-recon-r8
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r8)
[ -n "$RECON" ]
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "reconstruct r8 is live"
