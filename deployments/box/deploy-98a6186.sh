#!/usr/bin/env bash
# Deploys commit 98a6186a8eed to the box: several controllers built from one
# source (github.com/jalalirs/iocean-controllers), and a look at a
# repository's controllers before building. Run on the box:
#   bash ~/iocean/scratch/deploy-98a6186a8eed/deploy.sh
# Before it: this commit exported to ~/iocean/scratch/deploy-98a6186a8eed, its
# control-plane and mcp images built (not started), the new controller build
# image built (iocean/controller-build:dev), and the database backed up to
# ~/iocean/backups/coral-before-98a6186a8eed.dump. Safe to run twice.
set -euo pipefail
SHA=98a6186a8eed
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. migration 0038 (a build's controllers, one stack each)"
docker compose --env-file .env run --rm migrate

echo "2. the controller build image that builds every controller in a source"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
BUILD=$(docker images --no-trunc --format '{{.ID}}' iocean/controller-build:dev)
docker rm -f iocean-keep-controller-build >/dev/null 2>&1 || true
docker create --name iocean-keep-controller-build iocean/controller-build:dev true >/dev/null
sed -i "s|^IOCEAN_CONTROLLER_BUILD_IMAGE=.*|IOCEAN_CONTROLLER_BUILD_IMAGE=$BUILD|" "$ENV"
cp "$ENV" .env

echo "3. the control plane and MCP (the agent is unchanged)"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "4. checks"
sleep 8
BIND=$(sed -n 's/^IOCEAN_BIND_ADDRESS=//p' "$ENV"); BIND=${BIND:-127.0.0.1}
curl -fsS "http://$BIND:18080/api/v1/platform" | head -c 300; echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
