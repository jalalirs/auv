#!/usr/bin/env bash
# Run on the box, through ssh: rewrites manifest.json in the downloads folder
# from the installers that are there, so the site lists exactly what it can
# serve.
#
#   ssh box 'bash -s -- <version> <commit>' < tools/lib/downloads-manifest.sh
set -euo pipefail
VERSION="${1:?version}"
COMMIT="${2:?commit}"
cd ~/iocean/downloads

FILES=()
for f in iocean-mac-arm64.dmg iocean-mac-x64.dmg iocean-windows-x64.exe iocean-windows-arm64.exe iocean-linux-amd64.deb; do
    [ -f "$f" ] && FILES+=("$f")
done
[ "${#FILES[@]}" -gt 0 ] || { echo "no installers in ~/iocean/downloads" >&2; exit 1; }

{
    echo "{"
    echo "  \"version\": \"${VERSION}\","
    printf '  "files": ['; printf '"%s", ' "${FILES[@]}" | sed 's/, $//'; echo "],"
    echo "  \"sha256\": {"
    for i in "${!FILES[@]}"; do
        sep=","; [ "$i" -lt $(( ${#FILES[@]} - 1 )) ] || sep=""
        echo "    \"${FILES[$i]}\": \"$(sha256sum "${FILES[$i]}" | cut -d' ' -f1)\"${sep}"
    done
    echo "  },"
    echo "  \"builtAt\": \"$(date -u +%FT%TZ)\","
    echo "  \"commit\": \"${COMMIT}\""
    echo "}"
} >manifest.json.part
python3 -m json.tool manifest.json.part >/dev/null
mv manifest.json.part manifest.json
echo "manifest ${VERSION}: ${FILES[*]}"
