#!/usr/bin/env bash
# Makes simulator r9 the one every dive uses: r8 with coral/tasks/covering.py
# and coral/controllers/plan.py from c859e24. A search given a datum and a
# radius is flown as an expanding square out from the datum, lanes a camera
# footprint apart, and reports how much of the circle it searched, how far
# from the datum the thing was and where the vehicle marked it. Everything
# else flies as on r8. r8 stays to go back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r9/deploy-sim-r9.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r8 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-3c227e7/deployments/box

echo "1. no dive running"
if docker ps --format "{{.Image}}" | grep -q "sim-runtime"; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r9 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r9-candidate 127.0.0.1:18081/sim-runtime:r9
docker push -q 127.0.0.1:18081/sim-runtime:r9 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r9 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r9
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r9|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep "^IOCEAN_SIM_IMAGE="
docker ps --format "{{.Names}} {{.Status}}" | grep -E "^iocean-(control-plane|agent|mcp)"
echo "simulator r9 is live"
