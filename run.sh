#!/usr/bin/env bash
# Record only this top-level parent; nested run.sh calls inherit the guard.
# shellcheck source=/dev/null
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/_code/_maintenance/record-script-usage.sh"
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
    --help|-h) printf "Usage: %s [arguments]\nStable entry point for this independent Tumble Scripts repository.\n" "$(basename -- "$REPO_ROOT")"; exit 0 ;;
    --version) printf "%s %s\n" "$(basename -- "$REPO_ROOT")" "2026.07"; exit 0 ;;
esac
exec "$REPO_ROOT/launchers/copy-except-tar.sh" "$@"
