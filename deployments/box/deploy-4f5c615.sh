#!/usr/bin/env bash
# Deploys commit 4f5c615d3906 to the box: reconstructions, mappings, the map
# store, the composer's ground, GPU jobs on the worker. Run on the box:
#   bash ~/iocean/scratch/deploy-4f5c615d3906/deploy.sh
# Before it: this commit exported to ~/iocean/scratch/deploy-4f5c615d3906, its
# control-plane, worker and mcp images built (not started), and the database
# backed up to ~/iocean/backups/coral-before-4f5c615d3906.dump.
set -euo pipefail
SHA=4f5c615d3906
D=~/iocean/scratch/deploy-$SHA/deployments/box
ENV=~/code/auv/deployments/box/.env
SQL="docker exec -i iocean-record-1 psql -v ON_ERROR_STOP=1 -U coral -d coral"
cd "$D"

echo "1. migrations 0034, 0035, 0036"
docker compose --env-file .env run --rm migrate

echo "2. the places job with flat seabeds, store bases and every source by default"
OLD=$(sed -n 's/^IOCEAN_PLACES_IMAGE=//p' "$ENV")
printf 'FROM %s\nCOPY packages/places/iocean_places /opt/iocean/packages/places/iocean_places\n' "$OLD" > /tmp/places-$SHA.Dockerfile
docker build -q -f /tmp/places-$SHA.Dockerfile -t 127.0.0.1:18081/iocean-places:r3 ~/iocean/scratch/deploy-$SHA >/dev/null
docker push -q 127.0.0.1:18081/iocean-places:r3 >/dev/null
PLACES=$(docker inspect --format '{{index .RepoDigests 0}}' 127.0.0.1:18081/iocean-places:r3)

echo "3. the reconstruction image, by its content identity (already on this host, pinned)"
RECON=$(docker images --no-trunc --format '{{.ID}}' iocean/reconstruct-video:dev)
docker rm -f iocean-keep-reconstruct >/dev/null 2>&1 || true
docker create --name iocean-keep-reconstruct iocean/reconstruct-video:dev true >/dev/null

echo "4. settings (the old .env kept in ~/iocean/backups)"
cp "$ENV" ~/iocean/backups/env-before-$SHA
sed -i "s|^IOCEAN_PLACES_IMAGE=.*|IOCEAN_PLACES_IMAGE=$PLACES|" "$ENV"
if grep -q '^IOCEAN_RECONSTRUCT_IMAGE=' "$ENV"; then sed -i "s|^IOCEAN_RECONSTRUCT_IMAGE=.*|IOCEAN_RECONSTRUCT_IMAGE=$RECON|" "$ENV"; else echo "IOCEAN_RECONSTRUCT_IMAGE=$RECON" >> "$ENV"; fi
if grep -q '^IOCEAN_WORKER_JOB_GPUS=' "$ENV"; then sed -i "s|^IOCEAN_WORKER_JOB_GPUS=.*|IOCEAN_WORKER_JOB_GPUS=1|" "$ENV"; else echo "IOCEAN_WORKER_JOB_GPUS=1" >> "$ENV"; fi
cp "$ENV" .env

echo "5. the control plane and MCP, then the agent (running dives are adopted)"
docker compose --env-file .env up -d --no-deps control-plane mcp
sleep 5
docker compose --env-file .env up -d --no-deps agent

echo "6. Coral City may run a GPU job; the box has one card for jobs; the reefs are in the store"
$SQL <<'SQL'
UPDATE exec.quota SET max_gpu = greatest(max_gpu, 1), max_cpu = greatest(max_cpu, 16),
       max_memory_bytes = greatest(max_memory_bytes, 85899345920)
 WHERE org_id = 'org_01M17C7RF2YWSQ48WNRHCTFEX4';
UPDATE exec.target SET capacity_gpu = greatest(capacity_gpu, 1) WHERE name = 'box';
UPDATE catalog.city SET discoverable = true
 WHERE owned_by_org IS NULL AND retired_at IS NULL
   AND slug IN ('al-fahal', 'kaneohe', 'looe-key', 'red-sea', 'shushah', 'red-sea-video-reef');
SQL

echo "7. checks"
sleep 5
BIND=$(sed -n 's/^IOCEAN_BIND_ADDRESS=//p' "$ENV"); BIND=${BIND:-127.0.0.1}
curl -fsS "http://$BIND:18080/api/v1/platform" | head -c 300; echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "deployed $SHA"
