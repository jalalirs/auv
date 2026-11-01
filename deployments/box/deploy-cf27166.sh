#!/usr/bin/env bash
# Deploys commit cf271665ee6f to the box: people sign in only with Google, and
# whoever signs in under an address in IOCEAN_ADMIN_EMAILS is a platform
# administrator. Run on the box:
#   bash ~/iocean/scratch/deploy-cf271665ee6f/deployments/box/deploy-cf27166.sh
# Before it: this commit exported there, and the Google client given the
# redirect https://iocean.areen.ai/api/v1/auth/google/callback. No migration.
# The control-plane image is built here and the control plane restarts (about
# a minute without the API). Safe to run twice.
#
# To undo: docker tag iocean/control-plane:before-cf271665ee6f iocean/control-plane:r1,
# restore ~/iocean/backups/env-before-cf271665ee6f to the .env, and run step 3
# from ~/iocean/scratch/deploy-16b09c7fdd54/deployments/box.
set -euo pipefail
SHA=cf271665ee6f
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai
ADMINS=jalalirs@gmail.com

echo "1. who is an administrator"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
grep -q '^IOCEAN_ADMIN_EMAILS=' "$ENV" || echo "IOCEAN_ADMIN_EMAILS=$ADMINS" >> "$ENV"

echo "2. the control-plane image, keeping the one before"
docker image inspect iocean/control-plane:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/control-plane:r1 iocean/control-plane:before-$SHA
cd "$D"
cp "$ENV" .env
docker compose --env-file .env build control-plane

echo "3. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "4. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
docker exec iocean-control-plane-1 printenv IOCEAN_ADMIN_EMAILS | grep -qx "$ADMINS" \
  && echo "administrators: $ADMINS" || echo "WARNING: IOCEAN_ADMIN_EMAILS is not $ADMINS"
curl -s "$PUBLIC/api/v1/auth/google/start?client=desktop" -o /dev/null -w '%{redirect_url}\n' \
  | grep -q 'redirect_uri=https%3A%2F%2Fiocean.areen.ai' \
  && echo "google returns to $PUBLIC" || echo "WARNING: google does not return to $PUBLIC"
echo "deployed $SHA"
