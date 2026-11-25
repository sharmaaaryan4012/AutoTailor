#!/bin/bash
# Resolve script directory portably
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

caffeinate -dimsu "$PYTHON_BIN" -m src.main --limit 75 --max-delivered 7 "$@" >> "$SCRIPT_DIR/data/cron.log" 2>&1
