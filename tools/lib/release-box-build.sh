#!/usr/bin/env bash
# Run on the box, detached, by tools/release-box: packages the staged app for
# Windows (x64, arm64) and Linux (.deb, x64) in electron-builder's image, puts
# the installers in ~/iocean/downloads, lists them for the site and removes its
# own folder. Its log is ~/iocean/scratch/release-<version>.log, which
# `tools/release-box --collect` reads and then removes.
#
#   bash build.sh <version> <electron version> <commit> [<electron mirror>]
set -euo pipefail
VERSION="${1:?version}"
ELECTRON="${2:?electron version}"
COMMIT="${3:?commit}"
MIRROR="${4:-}"
WORK="${HOME}/iocean/scratch/release-${VERSION}"
IMAGE="electronuserland/builder:wine"
BUILDER="electron-builder@26.0.12"

say() { echo "-> $(date -u +%H:%M:%S) $*"; }
trap 'echo "FAILED at line ${LINENO}"' ERR
cd "${WORK}"

FREE_GB="$(df -BG --output=avail "${HOME}" | tail -1 | tr -dc 0-9)"
[ "${FREE_GB}" -ge 20 ] || { echo "only ${FREE_GB} GB free, not building"; false; }
for url in https://registry.npmjs.org https://github.com https://registry-1.docker.io/v2/; do
    code="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "${url}" || true)"
    say "reach ${url}: ${code}"
done

mkdir -p "${HOME}/iocean/cache/electron" "${HOME}/iocean/cache/electron-builder" "${HOME}/iocean/cache/npm"
say "packaging Windows and Linux"
docker run --rm --name "iocean-release-${VERSION}" --cpus 8 --memory 8g \
    -v "${WORK}/project:/project" \
    -v "${HOME}/iocean/cache/electron:/root/.cache/electron" \
    -v "${HOME}/iocean/cache/electron-builder:/root/.cache/electron-builder" \
    -v "${HOME}/iocean/cache/npm:/root/.npm" \
    ${MIRROR:+-e ELECTRON_MIRROR="${MIRROR}"} -w /project "${IMAGE}" bash -c "
        set -e
        b() { npx -y ${BUILDER} \"\$@\" -c.electronVersion=${ELECTRON} -c.npmRebuild=false 2>&1 | grep -v '^npm warn'; }
        trap 'chown -R \$(stat -c %u:%g /project) /project /root/.cache /root/.npm' EXIT
        b --win --x64 -c.directories.output=out/win-x64
        b --win --arm64 -c.directories.output=out/win-arm64
        b --linux --x64 -c.directories.output=out/linux"

cd "${WORK}/project/out"
install -m 644 win-x64/*.exe "${HOME}/iocean/downloads/iocean-windows-x64.exe.part"
install -m 644 win-arm64/*.exe "${HOME}/iocean/downloads/iocean-windows-arm64.exe.part"
install -m 644 linux/*.deb "${HOME}/iocean/downloads/iocean-linux-amd64.deb.part"
cd "${HOME}/iocean/downloads"
for f in iocean-windows-x64.exe iocean-windows-arm64.exe iocean-linux-amd64.deb; do mv "$f.part" "$f"; done
ls -lh iocean-windows-*.exe iocean-linux-*.deb | awk '{print "   " $NF " " $5}'
bash "${WORK}/downloads-manifest.sh" "${VERSION}" "${COMMIT}"
cd "${HOME}"
rm -rf "${WORK:?}"
say "DONE: iOcean ${VERSION} for Windows and Linux"
