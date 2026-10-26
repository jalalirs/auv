#!/usr/bin/env bash
# Deploys reconstruction image r9: r8 with lay.py and ml/splat/place_in_map.py
# from f94c6d2 and the commit after it. A strip whose edge fades has its ground
# lowered under its core only (within 3 m of a 10 m strip's centreline, not 5.3
# m), so no dark trench shows through the fade. Run on the box:
#   bash ~/iocean/scratch/recon-r9/deploy-recon-r9.sh
# No migration; only the control plane restarts. Safe to run twice.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box
[ -f ~/iocean/backups/env-before-recon-r9 ] || cp "$ENV" ~/iocean/backups/env-before-recon-r9
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r9)
[ -n "$RECON" ]
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "reconstruct r9 is live"
