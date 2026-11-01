#!/usr/bin/env bash
# Moves iOcean's public address to https://iocean.areen.ai (Cloud Run
# iocean-router, deployments/gcp/router, in front of the Funnel). Google sign-in
# returns there, and its cookies sit at the root. Run on the box:
#   bash ~/iocean/scratch/deploy-16b09c7fdd54/deployments/box/deploy-areen.sh
# Before it: https://iocean.areen.ai/api/v1/auth/google/callback added to the
# Google client. Same image as 16b09c7, no migration. Only the control plane
# restarts. Safe to run twice.
#
# To undo: restore ~/iocean/backups/env-before-areen to the .env and run step 2.
set -euo pipefail
D=~/iocean/scratch/deploy-16b09c7fdd54/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai

echo "1. Google returns to $PUBLIC"
[ -f ~/iocean/backups/env-before-areen ] || cp "$ENV" ~/iocean/backups/env-before-areen
sed -i "s|^IOCEAN_PUBLIC_URL=.*|IOCEAN_PUBLIC_URL=$PUBLIC|" "$ENV"
sed -i "s|^IOCEAN_GOOGLE_WEB_RETURN=.*|IOCEAN_GOOGLE_WEB_RETURN=$PUBLIC/#signed-in|" "$ENV"

echo "2. the control plane"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane

echo "3. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
curl -s "https://jalalirs.tailedf721.ts.net/iocean/api/v1/auth/google/start?client=desktop" -o /dev/null -w '%{redirect_url}\n' \
  | grep -q 'redirect_uri=https%3A%2F%2Fiocean.areen.ai%2Fapi' \
  && echo "google returns to $PUBLIC" || echo "WARNING: google does not return to $PUBLIC"
echo "deployed iocean.areen.ai"
