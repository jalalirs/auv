#!/usr/bin/env bash
# Makes simulator r5 the one every dive uses: r4 with coral/splat_pieces.py
# from 566a3a47b2c3. The water's veil goes onto splats through the colour
# matrix in proportion to each splat's brightness, not as an offset NuRec adds
# to every splat: a faded strip edge drew as a dark purple band, its far end
# as a pale patch. r4 stays in the registry to go back to. Run on the box:
#   bash ~/iocean/scratch/sim-r5/deploy-sim-r5.sh
# The worker restarts, so it refuses while a dive is running. Safe to run twice.
# To go back: set IOCEAN_SIM_IMAGE to ...sim-runtime:r4 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-0afc30ae06a4/deployments/box

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r5 in the registry"
docker push -q 127.0.0.1:18081/sim-runtime:r5 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r5 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r5
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r5|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r5 is live"
