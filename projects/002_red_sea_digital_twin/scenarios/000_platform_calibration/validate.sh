#!/usr/bin/env bash

set -euo pipefail

scenario_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stage_path="${scenario_dir}/stage.usda"

command -v usdcat >/dev/null
command -v usdchecker >/dev/null

if command -v sha256sum >/dev/null; then
    (cd "${scenario_dir}" && sha256sum --check checksums.sha256)
else
    (cd "${scenario_dir}" && shasum -a 256 --check checksums.sha256)
fi

usdcat --loadOnly "${stage_path}"
usdchecker --strict "${stage_path}"

printf 'Validated %s\n' "${stage_path}"
