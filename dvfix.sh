#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/dvfix.py" "$@"
fi

if command -v python >/dev/null 2>&1; then
    exec python "$SCRIPT_DIR/dvfix.py" "$@"
fi

echo "DVFix: could not find python3 or python on PATH." >&2
exit 127
