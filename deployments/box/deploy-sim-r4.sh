#!/usr/bin/env bash
# Makes simulator r4 the one every dive uses: r3 with the shell extension and
# coral/splat_pieces.py from ba06291. Splats rebuilt from a video are dimmed
# into the water by the camera's distance (the water's transmittance per
# channel, its veil laid in); before, a strip stayed bright from forty metres
# off. r3 stays in the registry to go back to. Run on the box:
#   bash ~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box/deploy-sim-r4.sh
# The worker restarts, so it refuses while a dive is running. Safe to run twice.
# To go back: set IOCEAN_SIM_IMAGE to ...sim-runtime:r3 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r3 in the registry"
docker push -q 127.0.0.1:18081/sim-runtime:r4 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r4 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r3
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r4|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r4 is live"
