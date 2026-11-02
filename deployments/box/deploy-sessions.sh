#!/usr/bin/env bash
# Sign-ins last a week instead of twelve hours (IOCEAN_SESSION_LIFETIME=168h,
# the compose default now). Run on the box:
#   bash ~/iocean/scratch/deploy-<sha>/deployments/box/deploy-sessions.sh <sha>
# Before it: that commit exported there. No image build and no migration: the
# control plane is only recreated with the new setting (about a minute without
# the API). Sessions already signed in keep the lifetime they were given. The
# agent, edge and MCP are not touched. Safe to run twice.
#
# To undo: run step 2 from ~/iocean/scratch/deploy-cf271665ee6f/deployments/box.
set -euo pipefail
SHA="${1:?usage: deploy-sessions.sh <sha>}"
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai

echo "1. the settings"
cd "$D"
cp "$ENV" .env

echo "2. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "3. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
docker exec iocean-control-plane-1 printenv IOCEAN_SESSION_LIFETIME | grep -qx 168h \
  && echo "sign-ins last 168h" || echo "WARNING: IOCEAN_SESSION_LIFETIME is not 168h"
curl -s -o /dev/null -w "api answers %{http_code} (401 is right: nobody signed in)\n" "$PUBLIC/api/v1/me"
echo "deployed $SHA"
