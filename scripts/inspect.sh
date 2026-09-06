#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 || "$1" == "--help" || "$1" == "-h" ]]; then
  echo 'Usage: ./scripts/inspect.sh /path/to/bundle (optional PORT=3001)'
  [[ $# == 1 && ( "$1" == "--help" || "$1" == "-h" ) ]] && exit 0
  exit 2
fi
command -v bun >/dev/null || { echo 'Install Bun first: https://bun.sh' >&2; exit 1; }
case "$1" in /*) bundle="$1" ;; *) bundle="$PWD/$1" ;; esac
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo/tools/inference-checker"
export NEXT_TELEMETRY_DISABLED=1
bun install --frozen-lockfile
exec bun run inspect -- "$bundle"
