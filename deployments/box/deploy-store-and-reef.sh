#!/usr/bin/env bash
# Your objects in the store (PUT/DELETE /api/v1/assets/{id}/store), and a
# dive in a world hands the runtime its reef as edited (brief.colonies). No
# migration. Rebuilds the control plane and the agent; MCP is unchanged.
#
# From the Mac, the commit exported to the box:
#   git archive 3c227e7 | ssh jalalirs@100.76.65.1 'mkdir -p ~/iocean/scratch/deploy-3c227e7 && tar -x -C ~/iocean/scratch/deploy-3c227e7'
# Then on the box:
#   bash ~/iocean/scratch/deploy-3c227e7/deployments/box/deploy-store-and-reef.sh 3c227e7
# Running dives are adopted by the new agent. The runtime only reads
# brief.colonies from sim-runtime r8; r7 ignores the key.
#
# To undo: docker tag iocean/control-plane:before-<sha> iocean/control-plane:r1
# (and iocean/worker), then step 3's `up`.
set -euo pipefail
SHA="${1:?usage: deploy-store-and-reef.sh <sha>}"
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai
cd "$D"
cp "$ENV" .env

echo "1. the images before, kept"
docker image inspect iocean/control-plane:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/control-plane:r1 iocean/control-plane:before-$SHA
docker image inspect iocean/worker:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/worker:r1 iocean/worker:before-$SHA

echo "2. the control plane and the agent, built"
docker compose --env-file .env build control-plane agent

echo "3. the control plane, then the agent"
docker compose --env-file .env up -d --no-deps control-plane
sleep 5
docker compose --env-file .env up -d --no-deps agent
# The edge's nginx holds the old containers' addresses until it reloads.
docker exec iocean-edge-1 nginx -s reload

echo "4. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
curl -s -o /dev/null -w "api answers %{http_code} (401 is right: nobody signed in)\n" "$PUBLIC/api/v1/me"
echo "deployed $SHA"
