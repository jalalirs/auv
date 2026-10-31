#!/usr/bin/env bash
# Deploys commit 16b09c7fdd54 to the box: Google sign-in through the public
# address https://jalalirs.tailedf721.ts.net/iocean (no tunnel), and the edge
# serving the product site and the Mac installer beside the API. Run on the box:
#   bash ~/iocean/scratch/deploy-16b09c7fdd54/deployments/box/deploy-16b09c7.sh
# Before it: this commit exported there, its control-plane image built as r1,
# the previous one kept as iocean/control-plane:before-16b09c7fdd54, and the
# redirect https://jalalirs.tailedf721.ts.net/iocean/api/v1/auth/google/callback
# added to the Google client. No migration. The control plane and the edge
# restart. Safe to run twice.
#
# To undo: docker tag iocean/control-plane:before-16b09c7fdd54 iocean/control-plane:r1,
# restore ~/iocean/backups/env-before-16b09c7fdd54 to the .env, and run step 3
# from ~/iocean/scratch/deploy-0806e69b50b8/deployments/box.
set -euo pipefail
SHA=16b09c7fdd54
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://jalalirs.tailedf721.ts.net/iocean

echo "1. where the site and the installer live"
mkdir -p ~/iocean/site ~/iocean/downloads

echo "2. Google returns to the public address"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_PUBLIC_URL=.*|IOCEAN_PUBLIC_URL=$PUBLIC|" "$ENV"
grep -q '^IOCEAN_GOOGLE_WEB_RETURN=' "$ENV" \
  || echo "IOCEAN_GOOGLE_WEB_RETURN=$PUBLIC/#signed-in" >> "$ENV"

echo "3. the control plane and the edge"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps control-plane edge

echo "4. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
curl -s "$PUBLIC/api/v1/auth/google/start?client=desktop" -o /dev/null -w '%{redirect_url}\n' \
  | grep -q 'redirect_uri=https%3A%2F%2Fjalalirs.tailedf721.ts.net%2Fiocean' \
  && echo "google returns to $PUBLIC" || echo "WARNING: google does not return to $PUBLIC"
curl -s -o /dev/null -w "site: %{http_code}\n" "$PUBLIC/"
echo "deployed $SHA"
