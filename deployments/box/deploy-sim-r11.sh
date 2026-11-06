#!/usr/bin/env bash
# Makes simulator r11 the one every dive uses: r10 with coral/runner.py,
# coral/systems/coral.py and coral/draw/coral.py from this commit. A reef drawn
# as a layer (Al Fahal, Shushah, Looe Key) takes a partial world: only the
# colonies edited, by coral-<n>, row n of the place's colonies.bin, and only
# when the world's digest is that file's. Everything else flies as on r10.
# r10 stays to go back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r11/deploy-sim-r11.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r10 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-3c227e7/deployments/box

echo "1. no dive running"
if docker ps --format "{{.Image}}" | grep -q "sim-runtime"; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r11 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r11-candidate 127.0.0.1:18081/sim-runtime:r11
docker push -q 127.0.0.1:18081/sim-runtime:r11 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r11 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r11
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r11|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep "^IOCEAN_SIM_IMAGE="
docker ps --format "{{.Names}} {{.Status}}" | grep -E "^iocean-(control-plane|agent|mcp)"
echo "simulator r11 is live"
