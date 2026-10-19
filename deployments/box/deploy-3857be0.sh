#!/usr/bin/env bash
# Deploys commit 3857be0c79a9 to the box: controllers built from a public
# GitHub repository or a zip (plan item 69), on top of 4f5c615. Run on the box:
#   bash ~/iocean/scratch/deploy-3857be0c79a9/deploy.sh
# Before it: this commit exported to ~/iocean/scratch/deploy-3857be0c79a9, its
# control-plane and mcp images built (not started), the controller build image
# built and pinned (iocean/controller-build:dev), and the database backed up to
# ~/iocean/backups/coral-before-3857be0c79a9.dump. Safe to run twice.
set -euo pipefail
SHA=3857be0c79a9
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. migration 0037 (controller builds, a stack's source)"
docker compose --env-file .env run --rm migrate

echo "2. settings (the .env before this deploy kept once in ~/iocean/backups)"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
BUILD=$(docker images --no-trunc --format '{{.ID}}' iocean/controller-build:dev)
docker rm -f iocean-keep-controller-build >/dev/null 2>&1 || true
docker create --name iocean-keep-controller-build iocean/controller-build:dev true >/dev/null
set_env() {
  if grep -q "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi
}
set_env IOCEAN_CONTROLLER_BUILD_IMAGE "$BUILD"
set_env IOCEAN_CONTROLLER_REGISTRY_PUSH "registry:5000"
set_env IOCEAN_CONTROLLER_REGISTRY_PULL "127.0.0.1:18081"
cp "$ENV" .env

echo "3. the control plane and MCP (the agent is unchanged)"
docker compose --env-file .env up -d --no-deps control-plane mcp

echo "4. checks"
sleep 8
BIND=$(sed -n 's/^IOCEAN_BIND_ADDRESS=//p' "$ENV"); BIND=${BIND:-127.0.0.1}
curl -fsS "http://$BIND:18080/api/v1/platform" | head -c 300; echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
