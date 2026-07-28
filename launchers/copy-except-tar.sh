#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/launchers/lib/terminal.sh"
export PYTHONPYCACHEPREFIX="$SCRIPT_DIR/cache/pycache"
relaunch_in_terminal_if_needed "$@"
exec python3 "$SCRIPT_DIR/python/copy-except-tar.py" "$@"
