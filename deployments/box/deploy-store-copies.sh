#!/usr/bin/env bash
# Store items are copied into yours: a store place becomes a place of your
# own with the store's published package; a store object becomes an object
# of yours. Migration 0044 adds copied_from and in_store.
# Run on the box:
#   bash ~/iocean/scratch/deploy-<sha>/deployments/box/deploy-store-copies.sh <sha>
# Before it: that commit exported there. The database is backed up, the
# control-plane image built (the one before kept), migration 0044 applied, and
# only the control plane restarts (about a minute without the API). Safe to
# run twice.
#
# To undo: docker tag iocean/control-plane:before-<sha> iocean/control-plane:r1,
# then the same `up` as step 4. Migration 0044 only adds columns and swaps one
# unique index for a partial one, so the old build runs on it.
set -euo pipefail
SHA="${1:?usage: deploy-store-copies.sh <sha>}"
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai
cd "$D"
cp "$ENV" .env

echo "1. the database, backed up"
DUMP=~/iocean/backups/coral-before-$SHA.dump
[ -s "$DUMP" ] || docker exec iocean-record-1 sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$DUMP"
ls -l "$DUMP"

echo "2. the control-plane image, keeping the one before"
docker image inspect iocean/control-plane:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/control-plane:r1 iocean/control-plane:before-$SHA
docker compose --env-file .env build control-plane

echo "3. migration 0044 (store items are copied into yours)"
docker compose --env-file .env run --rm migrate

echo "4. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "5. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
curl -s -o /dev/null -w "api answers %{http_code} (401 is right: nobody signed in)\n" "$PUBLIC/api/v1/me"
curl -s -o /dev/null -w "store objects answer %{http_code} (401 is right)\n" "$PUBLIC/api/v1/store/objects"
echo "deployed $SHA"
