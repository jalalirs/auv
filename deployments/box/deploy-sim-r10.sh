#!/usr/bin/env bash
# Makes simulator r10 the one every dive uses: r9 with coral/tasks/base.py,
# coral/tasks/going.py and coral/tasks/covering.py from 005a0c6. A survey over
# a reef point-counts the plot the camera saw and, given the last round's cover
# per plot, says how far each kind moved since; a survey can be done at enough
# of its box (enoughShare). Everything else flies as on r9. r9 stays to go
# back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r10/deploy-sim-r10.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r9 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-3c227e7/deployments/box

echo "1. no dive running"
if docker ps --format "{{.Image}}" | grep -q "sim-runtime"; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r10 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r10-candidate 127.0.0.1:18081/sim-runtime:r10
docker push -q 127.0.0.1:18081/sim-runtime:r10 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r10 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r10
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r10|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep "^IOCEAN_SIM_IMAGE="
docker ps --format "{{.Names}} {{.Status}}" | grep -E "^iocean-(control-plane|agent|mcp)"
echo "simulator r10 is live"
