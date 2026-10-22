#!/usr/bin/env bash
# Makes the simulator that draws laid assets the one every dive uses:
# 127.0.0.1:18081/sim-runtime:r1-candidate-recon (built 2026-10-18, its coral/
# code identical to the repository's) becomes sim-runtime:r2. r1 drew no reef
# rebuilt from a video and no structure, so nothing laid into a place showed in
# a dive. r1 stays in the registry to go back to. Run on the box:
#   bash ~/iocean/scratch/deploy-3b3004982e4d/deployments/box/deploy-sim-r2.sh
# The worker (agent) restarts, so it refuses while a dive is running. Safe to
# run twice. To go back: set IOCEAN_SIM_IMAGE to ...sim-runtime:r1 and run step 3.
set -euo pipefail
D=~/iocean/scratch/deploy-3b3004982e4d/deployments/box
ENV=~/code/auv/deployments/box/.env
cd "$D"

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r2 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r1-candidate-recon 127.0.0.1:18081/sim-runtime:r2
docker push -q 127.0.0.1:18081/sim-runtime:r2 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r2 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r2
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r2|" "$ENV"
cp "$ENV" .env

echo "3. the worker"
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r2 is live"
