#!/usr/bin/env bash
# Deploys two job images to the box:
#   places r5 (ecdce94): soundings interpolated across short triangles, not each
#     a flat tile (a 5 m survey came out as terraces); built on r4 with that
#     one file replaced.
#   reconstruct r6 (5c92710): a vehicle's run trains each splat one colour from
#     every side (its single view taught colours that showed green and pink).
# Run on the box:
#   bash ~/iocean/scratch/deploy-5bc7a09918f4/deployments/box/deploy-ecdce94-5bc7a09.sh
# No migration; only the control plane restarts, to read the new images. A job
# already running keeps the image it started with. Safe to run twice.
set -euo pipefail
SHA=5bc7a09918f4
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA

echo "1. places r5, pushed and named by digest"
docker push -q 127.0.0.1:18081/iocean-places:r5 >/dev/null
PLACES=$(docker inspect --format '{{index .RepoDigests 0}}' 127.0.0.1:18081/iocean-places:r5)
sed -i "s|^IOCEAN_PLACES_IMAGE=.*|IOCEAN_PLACES_IMAGE=$PLACES|" "$ENV"

echo "2. reconstruct r6, by its content identity"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r6)
[ -n "$RECON" ]
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env

echo "3. the control plane"
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker exec iocean-control-plane-1 env | grep -E '^IOCEAN_(PLACES|RECONSTRUCT)_IMAGE=' | cut -c1-70
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed places r5 and reconstruct r6"
