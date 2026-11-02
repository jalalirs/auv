#!/usr/bin/env bash
# Objects can be archived: POST /api/v1/assets/{id}/archive takes a reef, a
# structure or a survey out of its organisation's listings and keeps it.
# Run on the box:
#   bash ~/iocean/scratch/deploy-<sha>/deployments/box/deploy-objects-archive.sh <sha>
# Before it: that commit exported there. The database is backed up, the
# control-plane image built (the one before kept), migration 0043 applied, and
# only the control plane restarts (about a minute without the API). Safe to
# run twice.
#
# To undo: docker tag iocean/control-plane:before-<sha> iocean/control-plane:r1,
# then the same `up` as step 4. Migration 0043 only adds columns, so the old
# build runs on it (and lists archived objects again).
set -euo pipefail
SHA="${1:?usage: deploy-objects-archive.sh <sha>}"
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

echo "3. migration 0043 (an object can be archived)"
docker compose --env-file .env run --rm migrate

echo "4. the control plane"
docker compose --env-file .env up -d --no-deps control-plane

echo "5. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
curl -s -o /dev/null -w "api answers %{http_code} (401 is right: nobody signed in)\n" "$PUBLIC/api/v1/me"
curl -s -o /dev/null -w "archive route answers %{http_code} (401 is right)\n" -X POST "$PUBLIC/api/v1/assets/none/archive"
echo "deployed $SHA"
