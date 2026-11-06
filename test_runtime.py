"""Check standalone GDAL detection and non-macOS path selection."""
import unittest
from unittest.mock import patch

import app
import osgeo
from osgeo import gdal
from gdb_reader import environment


class RuntimeTests(unittest.TestCase):
    def test_standalone_gdal_does_not_require_qgis_path(self):
        with patch.object(osgeo, '__file__', '/opt/example/osgeo/__init__.py'):
            env = environment()
        self.assertTrue(env['ready'], env)
        self.assertFalse(env['qgis_runtime'])

    def test_old_gdal_is_not_ready(self):
        original = gdal.VersionInfo
        def version(key):
            return '3050000' if key == 'VERSION_NUM' else original(key)
        with patch.object(gdal, 'VersionInfo', side_effect=version):
            self.assertFalse(environment()['ready'])

    def test_non_macos_browser_uses_standard_browser(self):
        with patch.object(app.sys, 'platform', 'linux'), patch.object(app.webbrowser, 'open') as opened:
            app.open_browser('http://127.0.0.1:8765')
            opened.assert_called_once_with('http://127.0.0.1:8765')


if __name__ == '__main__':
    unittest.main()
