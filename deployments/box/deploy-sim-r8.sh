#!/usr/bin/env bash
# Makes simulator r8 the one every dive uses: r7 with coral/runner.py,
# coral/systems/coral.py and coral/draw/coral.py from 5a06d78. A dive in a
# world draws its reef as the world edited it (brief.colonies): colonies
# moved, sized and turned on their own base, new ones as copies of a built
# colony of their form, hidden or dropped ones not drawn and nothing to hit.
# A dive with no brief.colonies is drawn as on r7. r7 stays to go back to.
# Run on the box:
#   bash ~/iocean/scratch/sim-r8/deploy-sim-r8.sh
# Only the worker restarts (--no-deps agent), so it refuses while a dive is
# running. Safe to run twice. To go back: set IOCEAN_SIM_IMAGE to
# ...sim-runtime:r7 and run step 3.
set -euo pipefail
ENV=~/code/auv/deployments/box/.env
D=~/iocean/scratch/deploy-3c227e7/deployments/box

echo "1. no dive running"
if docker ps --format "{{.Image}}" | grep -q "sim-runtime"; then
  echo "a dive is running; run this again when it has finished"; exit 1
fi

echo "2. r8 in the registry"
docker tag 127.0.0.1:18081/sim-runtime:r8-candidate 127.0.0.1:18081/sim-runtime:r8
docker push -q 127.0.0.1:18081/sim-runtime:r8 >/dev/null
[ -f ~/iocean/backups/env-before-sim-r8 ] || cp "$ENV" ~/iocean/backups/env-before-sim-r8
sed -i "s|^IOCEAN_SIM_IMAGE=.*|IOCEAN_SIM_IMAGE=127.0.0.1:18081/sim-runtime:r8|" "$ENV"

echo "3. the worker"
cd "$D"
cp "$ENV" .env
docker compose --env-file .env up -d --no-deps agent

echo "4. checks"
sleep 6
docker exec iocean-agent-1 env | grep "^IOCEAN_SIM_IMAGE="
docker ps --format "{{.Names}} {{.Status}}" | grep -E "^iocean-(control-plane|agent|mcp)"
echo "simulator r8 is live"
