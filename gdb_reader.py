"""OpenFileGDB read-only inspection. No writes, SQL or feature values in output."""
import sys
from datetime import datetime
from pathlib import Path
from config import EXPECTED_GDAL_MAJOR_MINOR, MIN_GDAL_VERSION_NUM, VERSION
from statistics import tally_feature, finish_stats


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def environment():
    result = {"program_version": VERSION, "python_path": sys.executable,
              "python_version": sys.version, "read_only": True, "ready": False}
    try:
        import osgeo
        from osgeo import gdal, ogr
        gdal.UseExceptions()
        module = str(Path(osgeo.__file__).resolve())
        version = gdal.VersionInfo("RELEASE_NAME")
        supported = int(gdal.VersionInfo("VERSION_NUM")) >= MIN_GDAL_VERSION_NUM
        driver = gdal.GetDriverByName("OpenFileGDB")
        fd = ogr.FieldDefn("probe", ogr.OFTString)
        alias_api = hasattr(fd, "GetAlternativeName") or hasattr(fd, "GetAlternativeNameRef")
        from_qgis = ".app/Contents/" in module and "qgis" in module.lower()
        result.update(gdal_version=version, osgeo_path=module, openfilegdb=bool(driver),
                      alias_api=alias_api, qgis_runtime=from_qgis,
                      ready=bool(driver) and supported)
        warnings = []
        if not supported:
            warnings.append("需要 GDAL 3.6 或更新版本及 OpenFileGDB 驱动")
        if not version.startswith(EXPECTED_GDAL_MAJOR_MINOR + "."):
            warnings.append("GDAL 版本与开发基线 3.12 不同，请核验兼容性")
        if not alias_api:
            warnings.append("当前 GDAL Python 绑定未提供字段别名接口；别名保留为空")
        result["warnings"] = warnings
    except Exception as exc:
        result["error"] = str(exc)
    return result


def source_alias(definition):
    for name in ("GetAlternativeName", "GetAlternativeNameRef"):
        method = getattr(definition, name, None)
        if method:
            return method() or None
    return None


def make_field(index, name, alias, kind, role="attribute"):
    system = role != "attribute" or name.casefold() in {
        "objectid", "shape", "shape_length", "shape_area", "globalid"}
    return {"field_index": index, "field_name": name, "field_alias": alias,
            "field_type": kind, "field_category": "系统字段" if system else "普通属性字段",
            "role": role, "status": "success", "null_count": 0,
            "empty_string_count": 0, "whitespace_string_count": 0}


def inspect_gdb(item, env, progress, log):
    from osgeo import gdal, ogr
    gdal.UseExceptions()
    ogr.UseExceptions()
    result = dict(item, driver=None, status="success", layers=[], errors=[],
                  read_time=now(), gdal_version=env.get("gdal_version"))

    def error(code, message, layer=None, field=None):
        entry = {"code": code, "message": message, "path": item["path"],
                 "layer_name": layer, "field_name": field, "time": now()}
        result["errors"].append(entry)
        log("异常 " + str(entry))
        return entry

    log("GDB 开始 " + item["path"])
    ds = None
    try:
        if not Path(item["path"]).is_dir():
            error("GDB_NOT_FOUND", "GDB 不存在")
            result["status"] = "failed"
            return result
        if not gdal.GetDriverByName("OpenFileGDB"):
            error("DRIVER_NOT_FOUND", "OpenFileGDB 驱动不可用")
            result["status"] = "failed"
            return result
        try:
            ds = gdal.OpenEx(item["path"], gdal.OF_VECTOR | gdal.OF_READONLY,
                             allowed_drivers=["OpenFileGDB"])
            if ds is None:
                raise RuntimeError(gdal.GetLastErrorMsg() or "无法打开 GDB")
        except Exception as exc:
            error("PERMISSION_DENIED" if isinstance(exc, PermissionError) else "GDB_OPEN_FAILED", str(exc))
            result["status"] = "failed"
            return result
        result["driver"] = ds.GetDriver().ShortName
        total = ds.GetLayerCount()
        for index in range(total):
            record = {"layer_index": index + 1, "layer_name": "#" + str(index + 1),
                      "object_type": "other", "geometry_type": "Unknown", "fields": [],
                      "feature_count": None, "status": "success", "read_time": now(), "errors": []}
            result["layers"].append(record)
            layer = None
            before_errors = len(result["errors"])
            try:
                layer = ds.GetLayerByIndex(index)
                if layer is None:
                    raise RuntimeError("图层无法读取")
                record["layer_name"] = layer.GetName()
                log("图层开始 " + record["layer_name"])
                progress(layer_name=record["layer_name"], layer_current=index + 1,
                         layer_total=total, records_read=0)
                definition = layer.GetLayerDefn()
                spatial = definition.GetGeomFieldCount() > 0
                record.update(object_type="spatial_layer" if spatial else "non_spatial_table",
                              geometry_type=ogr.GeometryTypeToName(definition.GetGeomType()))
                fields = record["fields"]
                for fi in range(definition.GetFieldCount()):
                    name = "#" + str(fi)
                    stat = make_field(fi, name, None, "Unknown")
                    try:
                        fd = definition.GetFieldDefn(fi)
                        name = fd.GetName()
                        stat.update(field_name=name, field_type=fd.GetTypeName(),
                                    field_category=make_field(fi, name, None, "")["field_category"])
                        stat["field_alias"] = source_alias(fd)
                    except Exception:
                        stat["status"] = "failed"
                        error("FIELD_READ_FAILED", "字段元数据读取失败", record["layer_name"], name)
                    fields.append(stat)
                # OGR exposes the FID and geometry outside ordinary attribute fields.
                # Preserve them explicitly, without inventing aliases.
                fid_name = layer.GetFIDColumn()
                if fid_name and fid_name not in {s["field_name"] for s in fields}:
                    fields.append(make_field(-1, fid_name, None, "FID", "fid"))
                for gi in range(definition.GetGeomFieldCount()):
                    gd = definition.GetGeomFieldDefn(gi)
                    fields.append(make_field(gi, gd.GetName(), source_alias(gd),
                                             ogr.GeometryTypeToName(gd.GetType()), "geometry"))
                # A non-forced count avoids a second full scan on drivers without a fast count.
                try:
                    expected = layer.GetFeatureCount(0)
                except Exception:
                    expected = -1
                record["reported_feature_count"] = expected if expected >= 0 else None
                actual = 0
                try:
                    layer.ResetReading()
                    gdal.ErrorReset()
                    while True:
                        feature = layer.GetNextFeature()
                        if feature is None:
                            if gdal.GetLastErrorType() >= gdal.CE_Failure:
                                raise RuntimeError("GDAL 报告要素流读取失败")
                            break
                        actual += 1
                        tally_feature(feature, fields, lambda stat: error(
                            "FIELD_READ_FAILED", "字段值读取失败（不记录原始值）",
                            record["layer_name"], stat["field_name"]))
                        feature = None
                        if actual % 2000 == 0:
                            progress(records_read=actual)
                    if expected >= 0 and actual != expected:
                        raise RuntimeError("元数据记录数与实际读取数不一致：%s / %s" % (expected, actual))
                    record["feature_count"] = actual
                    finish_stats(fields, actual)
                except Exception:
                    finish_stats(fields, actual, complete=False)
                    record.update(status="failed", feature_count=None, partial_records_read=actual)
                    error("STATISTICS_FAILED", "统计未完整完成；部分计数不作为结果", record["layer_name"])
                progress(records_read=actual)
                log("图层结束 %s 记录数=%s 字段数=%s" % (
                    record["layer_name"], record["feature_count"], len(fields)))
            except Exception as exc:
                record["status"] = "failed"
                finish_stats(record["fields"], 0, complete=False)
                error("LAYER_READ_FAILED", str(exc), record["layer_name"])
            finally:
                layer = None
                record["errors"] = result["errors"][before_errors:]
                if record["errors"] and record["status"] == "success":
                    record["status"] = "partial"
        if result["errors"]:
            result["status"] = "partial"
    except Exception as exc:
        error("UNKNOWN_ERROR", str(exc))
        result["status"] = "failed"
    finally:
        ds = None
        result["finished_time"] = now()
        result["summary"] = {
            "spatial_layers": sum(l["object_type"] == "spatial_layer" for l in result["layers"]),
            "tables": sum(l["object_type"] == "non_spatial_table" for l in result["layers"]),
            "layers": len(result["layers"]),
            "fields": sum(len(l["fields"]) for l in result["layers"]),
            "errors": len(result["errors"])}
        log("GDB 结束 " + item["path"] + " 状态=" + result["status"])
    return result
