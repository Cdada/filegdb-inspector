#!/usr/bin/env bash
set -eu
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
export PYTHONDONTWRITEBYTECODE=1
if [ -n "${GDB_INSPECTOR_PYTHON:-}" ]; then
    exec "$GDB_INSPECTOR_PYTHON" -B "$APP_DIR/app.py" "$@"
fi
if [ "$(uname -s)" = "Darwin" ]; then
    exec bash "$APP_DIR/start.command" "$@"
fi
exec python3 -B "$APP_DIR/app.py" "$@"
