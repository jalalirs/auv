#!/usr/bin/env bash
# Worlds: a place has one world (migration 0045), and what a world is built
# from is kept as assets: public and derived bathymetry, cover maps, species
# lists (migration 0046, reconstruct image r11 with the import job for them).
# Run on the box:
#   bash ~/iocean/scratch/deploy-<sha>/deployments/box/deploy-worlds.sh <sha>
# Before it: that commit exported there, and iocean/reconstruct-video:r11
# built. The database is backed up, the control-plane image built (the one
# before kept), the migrations applied, and the control plane and MCP restart.
# Safe to run twice.
#
# To undo: docker tag iocean/control-plane:before-<sha> iocean/control-plane:r1 (and mcp),
# put the env back from ~/iocean/backups/env-before-<sha>, then step 5's `up`.
# Both migrations only add, so the old build runs on them.
set -euo pipefail
SHA="${1:?usage: deploy-worlds.sh <sha>}"
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
PUBLIC=https://iocean.areen.ai
cd "$D"

echo "1. the database and the env, backed up"
DUMP=~/iocean/backups/coral-before-$SHA.dump
[ -s "$DUMP" ] || docker exec iocean-record-1 sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$DUMP"
ls -l "$DUMP"
[ -f ~/iocean/backups/env-before-$SHA ] || cp "$ENV" ~/iocean/backups/env-before-$SHA

echo "2. reconstruct r11 for imports"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:r11)
[ -n "$RECON" ]
sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"
cp "$ENV" .env

echo "3. the control-plane image, keeping the one before"
docker image inspect iocean/control-plane:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/control-plane:r1 iocean/control-plane:before-$SHA
docker image inspect iocean/mcp:before-$SHA >/dev/null 2>&1 \
  || docker tag iocean/mcp:r1 iocean/mcp:before-$SHA
docker compose --env-file .env build control-plane mcp

echo "4. migrations 0045 (a place is a world) and 0046 (a foundation is an asset)"
docker compose --env-file .env run --rm migrate

echo "5. the control plane, and MCP with worlds_get and worlds_save"
docker compose --env-file .env up -d --no-deps control-plane mcp

# The edge's nginx holds the old containers' addresses until it reloads:
# without this the API answers 405 and MCP 404.
docker exec iocean-edge-1 nginx -s reload

echo "6. checks"
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|edge|agent|mcp)'
docker exec iocean-control-plane-1 env | grep '^IOCEAN_RECONSTRUCT_IMAGE=' | cut -c1-40
curl -s -o /dev/null -w "api answers %{http_code} (401 is right: nobody signed in)\n" "$PUBLIC/api/v1/me"
echo "deployed $SHA"
