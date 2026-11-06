"""Loopback-only configuration for QGIS or standalone GDAL runtimes."""
import os
import sys
from pathlib import Path

VERSION = "1.1.0"
BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.environ.get("GDB_INSPECTOR_RUNTIME_DIR", str(BASE_DIR / "runtime"))).expanduser().resolve()
HOST = "127.0.0.1"
PORT = int(os.environ.get("GDB_INSPECTOR_PORT", "8765"))
QGIS_APP_PATH = os.environ.get("QGIS_APP_PATH")
EXPECTED_GDAL_MAJOR_MINOR = "3.12"
MIN_GDAL_VERSION_NUM = 3060000
ALLOW_MANUAL_PATH = os.environ.get("GDB_INSPECTOR_MANUAL_PATH", "0" if sys.platform == "darwin" else "1") == "1"
