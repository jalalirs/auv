#!/usr/bin/env bash
# Deploys commit 0e03750 to the box: the reconstruction job's camera solve on
# 150 tracks a frame with two refinement rounds (45 min, not 4.5 h, on the Red
# Sea video). The image, iocean/reconstruct-video:r2, is built and pinned
# (iocean-keep-reconstruct-r2). Run on the box:
#   bash ~/iocean/scratch/deploy-f0607bd2c495/deploy-0e03750.sh
# No migration; only the control plane restarts, to read the new image. A
# reconstruction already running keeps the image it started with. Safe to run
# twice.
set -euo pipefail
D=~/iocean/scratch/deploy-f0607bd2c495/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. the reconstruction image, by its content identity"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r2)
[ -f ~/iocean/backups/env-before-0e03750 ] || cp "$ENV" ~/iocean/backups/env-before-0e03750
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env

echo "2. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "3. checks"
sleep 8
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed 0e03750"
