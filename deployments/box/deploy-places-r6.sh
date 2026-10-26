#!/usr/bin/env bash
# Deploys places r6 (a864e04): r5 with build.py replaced. An optional source
# that sees nothing of a square (a satellite over open water) is left out and
# said so, and the global grid makes the seabed; a build of open water no
# longer fails. Run on the box:
#   bash ~/iocean/scratch/places-r6/deploy-places-r6.sh
# No migration; only the control plane restarts. Safe to run twice.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box
[ -f ~/iocean/backups/env-before-places-r6 ] || cp "$ENV" ~/iocean/backups/env-before-places-r6
docker push -q 127.0.0.1:18081/iocean-places:r6 >/dev/null
PLACES=$(docker inspect --format '{{index .RepoDigests 0}}' 127.0.0.1:18081/iocean-places:r6)
sed -i "s|^IOCEAN_PLACES_IMAGE=.*|IOCEAN_PLACES_IMAGE=$PLACES|" "$ENV"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_PLACES_IMAGE=' | cut -c1-70
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "places r6 is live"
