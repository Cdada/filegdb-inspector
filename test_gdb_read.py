"""Run with QGIS Python; creates only a NEW synthetic GDB in a temp directory."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from osgeo import ogr, gdal
from gdb_reader import environment, inspect_gdb
from gdb_scanner import find_gdbs, validate_selection


def create_fixture(folder):
    gdal.UseExceptions()
    ogr.UseExceptions()
    path = Path(folder).resolve() / "中文 样例.gdb"
    if path.exists():
        raise FileExistsError(path)
    driver = ogr.GetDriverByName("OpenFileGDB")
    ds = driver.CreateDataSource(str(path))
    for name, kind, wkt in [
        ("中文点图层", ogr.wkbPoint, "POINT (0 0)"),
        ("线图层", ogr.wkbLineString, "LINESTRING (0 0,1 1)"),
        ("面图层", ogr.wkbPolygon, "POLYGON ((0 0,1 0,1 1,0 0))"),
        ("普通表", ogr.wkbNone, None), ("空图层", ogr.wkbPoint, None)]:
        layer = ds.CreateLayer(name, geom_type=kind)
        fd = ogr.FieldDefn("说明", ogr.OFTString)
        fd.SetAlternativeName("中文源数据别名")
        layer.CreateField(fd)
        layer.CreateField(ogr.FieldDefn("数量", ogr.OFTInteger))
        boolean = ogr.FieldDefn("开关", ogr.OFTInteger)
        boolean.SetSubType(ogr.OFSTBoolean)
        layer.CreateField(boolean)
        if name == "空图层":
            continue
        for val in (None, "", "   ", "正常"):
            feature = ogr.Feature(layer.GetLayerDefn())
            if val is not None:
                feature.SetField("说明", val)
            feature.SetField("数量", 0)
            feature.SetField("开关", 0)
            if wkt:
                feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            assert layer.CreateFeature(feature) == 0
            feature = None
        layer = None
    ds = None
    return path


def snapshot(path):
    return {str(p.relative_to(path)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in path.rglob("*") if p.is_file()}


class GDBTests(unittest.TestCase):
    def test_real_gdb_readonly_alias_nulls_tables(self):
        with tempfile.TemporaryDirectory(prefix="gdb inspector ") as temp:
            path = create_fixture(temp)
            before = snapshot(path)
            scan = find_gdbs(temp)
            item = validate_selection([str(path)], scan)[0]
            result = inspect_gdb(item, environment(), lambda **kw: None, lambda line: None)
            self.assertEqual(result["status"], "success", result["errors"])
            self.assertEqual(result["driver"], "OpenFileGDB")
            self.assertEqual(result["summary"]["tables"], 1)
            self.assertEqual(result["summary"]["spatial_layers"], 4)
            for layer in result["layers"]:
                fields = {f["field_name"]: f for f in layer["fields"]}
                self.assertEqual(fields["说明"]["field_alias"], "中文源数据别名")
                self.assertIsNone(fields["数量"]["field_alias"])
                if layer["layer_name"] == "空图层":
                    self.assertEqual(layer["feature_count"], 0)
                    self.assertIsNone(fields["数量"]["null_rate"])
                else:
                    self.assertEqual(layer["feature_count"], 4)
                    self.assertEqual(fields["说明"]["null_count"], 1)
                    self.assertEqual(fields["说明"]["blank_string_count"], 2)
                    self.assertEqual(fields["说明"]["null_rate"], .25)
                    self.assertEqual(fields["说明"]["blank_rate"], .75)
                    self.assertEqual(fields["数量"]["null_count"], 0)
                    self.assertEqual(fields["开关"]["null_count"], 0)
                self.assertTrue(any(f["role"] == "fid" for f in layer["fields"]))
            self.assertEqual(before, snapshot(path), "源文件内容、mtime 或文件列表发生变化")

    def test_scan_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "一级" / "A.GDB" / "内部.gdb").mkdir(parents=True)
            (root / "循环").symlink_to(root, target_is_directory=True)
            (root / "链接.gdb").symlink_to(root / "一级" / "A.GDB", target_is_directory=True)
            scan = find_gdbs(root)
            self.assertEqual(len(scan["gdbs"]), 1)
            self.assertEqual(len(find_gdbs(root / "一级" / "A.GDB")["gdbs"]), 1)
            with self.assertRaises(ValueError):
                validate_selection([str(root / "链接.gdb")], scan)


if __name__ == "__main__":
    print(json.dumps(environment(), ensure_ascii=False, indent=2))
    unittest.main()
