#!/usr/bin/env bash
# Builds the controller build job's image: the controller base first, saved
# as an OCI layout into the build context, then the job image around it.
#   bash packages/controller-build/build.sh [TAG]     (from the repository root)
set -euo pipefail
TAG=${1:-dev}
ROOT=$(pwd)
CONTEXT=$(mktemp -d "${TMPDIR:-/tmp}/controller-build-XXXXXX")
trap 'rm -rf "${CONTEXT:?}"' EXIT
mkdir -p "$CONTEXT/packages" "$CONTEXT/services/sim-runtime" "$CONTEXT/base-oci"
rsync -a --exclude __pycache__ --exclude '*.pyc' packages/sdk-python packages/controller-build "$CONTEXT/packages/"
rsync -a --exclude __pycache__ --exclude '*.pyc' --exclude 'test_*.py' services/sim-runtime/coral "$CONTEXT/services/sim-runtime/"
docker build -q --target base -t "iocean/controller-base:$TAG" -f packages/controller-build/Dockerfile "$CONTEXT" >/dev/null
docker save "iocean/controller-base:$TAG" | tar -x -C "$CONTEXT/base-oci"
docker build -q --target job -t "iocean/controller-build:$TAG" -f packages/controller-build/Dockerfile "$CONTEXT"
cd "$ROOT"
