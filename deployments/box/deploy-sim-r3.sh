#!/usr/bin/env bash
# Makes simulator r3 the one every dive uses: r2 with tasks/going.py from
# 9ca3bf6. A waypoint the vehicle tried for and missed (its navigation drifted)
# is passed over once it truly reaches a later one, recorded as missed with how
# close it came; before, the judge sat on it and every later point went
# uncounted (SubPipe: 1 of 4 though it flew the whole line). r2 stays in the
# registry to go back to. Run on the box:
#   bash ~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box/deploy-sim-r3.sh
# The worker (agent) restarts, so it refuses while a dive is running. Safe to
# run twice. To go back: set IOCEAN_SIM_IMAGE to ...sim-runtime:r2 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-9ca3bf688f6c/deployments/box

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r3 in the registry"
docker push -q 127.0.0.1:18081/sim-runtime:r3 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r3 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r3
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r3|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r3 is live"
