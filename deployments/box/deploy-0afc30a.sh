#!/usr/bin/env bash
# Deploys commit 0afc30ae06a4 to the box: the control plane refuses a dive whose
# objective the runtime has no judge for (an unknown kind, or a waypoint given
# as [x, y, z] instead of {"x", "y", "depthM"}), rather than flying it on a GPU
# and reporting "succeeded" with no score. Run on the box:
#   bash ~/iocean/scratch/deploy-0afc30ae06a4/deployments/box/deploy-0afc30a.sh
# The image is already built. No migration; only the control plane restarts.
set -euo pipefail
D=~/iocean/scratch/deploy-0afc30ae06a4/deployments/box
cd "$D"
cp ~/code/auv/deployments/box/.env .env
docker compose --env-file .env up -d --no-deps control-plane
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed 0afc30ae06a4"
