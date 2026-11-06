#!/bin/bash
set -eu
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
QGIS_ROOT="${QGIS_APP_PATH:-}"
if [ -z "$QGIS_ROOT" ]; then
    for candidate in /Applications/QGIS.app /Applications/QGIS-LTR.app "$HOME/Applications/QGIS.app"; do
        if [ -x "$candidate/Contents/MacOS/python" ]; then
            QGIS_ROOT="$candidate"
            break
        fi
    done
fi
if [ -z "$QGIS_ROOT" ] || [ ! -x "$QGIS_ROOT/Contents/MacOS/python" ]; then
    echo '未找到 QGIS Python。请设置 QGIS_APP_PATH 为 QGIS.app 的完整路径。'
    read -r -p '按回车退出。' ignored
    exit 1
fi
export QGIS_APP_PATH="$QGIS_ROOT"
# QGIS's wrapper configures PYTHONHOME to its bundled libraries.
exec "$QGIS_ROOT/Contents/MacOS/python" -B "$APP_DIR/app.py" "$@"
