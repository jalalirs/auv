#!/usr/bin/env bash
# Makes simulator r6 the one every dive uses: r5 with coral/world.py,
# coral/draw/things.py and coral/tasks/inspecting.py from the r6 commit. A
# pipeline can say where it is out of the sand, what is on it, and that the
# place's reconstruction already draws it; following one is tracking it: the
# vehicle is told the line as charted, sweeps across it until the camera has
# the pipe, and moves onto what it saw. r5 stays in the registry to go back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r6/deploy-sim-r6.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r5 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-cf271665ee6f/deployments/box

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r6 in the registry"
docker image inspect 127.0.0.1:18081/sim-runtime:r6 >/dev/null 2>&1 \
  || docker tag 127.0.0.1:18081/sim-runtime:r6-candidate 127.0.0.1:18081/sim-runtime:r6
docker push -q 127.0.0.1:18081/sim-runtime:r6 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r6 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r6
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r6|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r6 is live"
