#!/usr/bin/env bash
# Makes simulator r7 the one every dive uses: r6 with coral/runner.py,
# coral/controllers/plan.py, coral/tasks/__init__.py, coral/tasks/going.py,
# coral/tasks/mission.py and coral/systems/coral.py. A mission asks its stage
# again when the stage changes its mind (a pipe tracker that has found the pipe
# stops sweeping); a stage can say how much tether to pay out; a line is flown
# from its start; a transect counts only what it flew on the line, may be held
# at a depth, and over a reef reports the share of the line over each kind of
# colony (line intercept). r6 stays in the registry to go back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r7/deploy-sim-r7.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r6 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-08a360748125/deployments/box

echo "1. no dive running"
if docker ps --format '{{.Image}}' | grep -q 'sim-runtime'; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r7 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r7-candidate 127.0.0.1:18081/sim-runtime:r7
docker push -q 127.0.0.1:18081/sim-runtime:r7 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r7 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r7
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r7|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep '^IOCEAN_SIM_IMAGE='
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^iocean-(control-plane|agent|mcp)'
echo "simulator r7 is live"
