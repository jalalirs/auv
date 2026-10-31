#!/usr/bin/env bash
# Deploys commit 0806e69b50b8 to the box: sign in with Google. A first sign-in
# makes a person and a space of their own with ten dives a month; institutions
# approve people by address. Run on the box:
#   bash ~/iocean/scratch/deploy-0806e69b50b8/deployments/box/deploy-0806e69.sh
# Before it: this commit exported there, its control-plane image built as r1,
# the previous one kept as iocean/control-plane:before-0806e69b50b8, and the
# database backed up to ~/iocean/backups/coral-before-0806e69b50b8.dump. The
# Google client, IOCEAN_PUBLIC_URL and the starter queue and vehicles are in
# the .env. Only the control plane restarts. Safe to run twice.
#
# To undo: docker tag iocean/control-plane:before-0806e69b50b8 iocean/control-plane:r1,
# then the same `up` as step 2. Migration 0042 only adds, so the old build runs on it.
set -euo pipefail
SHA=0806e69b50b8
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"
cp "$ENV" .env

echo "1. migration 0042 (Google sign-in, approvals, a monthly dive limit)"
docker compose --env-file .env run --rm migrate

echo "2. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "3. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
# Google sign-in is on when the start sends the browser to Google.
curl -s -o /dev/null -w 'google start: %{http_code} %{redirect_url}\n' \
  "http://100.76.65.1:18080/api/v1/auth/google/start?client=web" | cut -c1-70
echo "deployed $SHA"
