#!/usr/bin/env bash
# Deploys commit f0607bd2c495 to the box: a place built on another keeps the
# coral atlas (the places image, r4), and MCP's places_build asks for a flat
# seabed. Run on the box:
#   bash ~/iocean/scratch/deploy-f0607bd2c495/deploy.sh
# Before it: the commit exported to ~/iocean/scratch/deploy-f0607bd2c495, the
# mcp image built, and 127.0.0.1:18081/iocean-places:r4 built (not pushed).
# No migration. Safe to run twice.
set -euo pipefail
SHA=f0607bd2c495
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. the places image with the coral fix, pushed and named by digest"
docker push -q 127.0.0.1:18081/iocean-places:r4 >/dev/null
PLACES=$(docker inspect --format '{{index .RepoDigests 0}}' 127.0.0.1:18081/iocean-places:r4)
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_PLACES_IMAGE=.*|IOCEAN_PLACES_IMAGE=$PLACES|" "$ENV"
cp "$ENV" .env

echo "2. the control plane (to read the new image) and MCP"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "3. checks"
sleep 8
BIND=$(sed -n 's/^IOCEAN_BIND_ADDRESS=//p' "$ENV"); BIND=${BIND:-127.0.0.1}
curl -fsS "http://$BIND:18080/api/v1/platform" | head -c 300; echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
