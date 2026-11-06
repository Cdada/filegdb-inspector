"""One streaming pass; numeric zero and False are never NULL."""


def tally_feature(feature, fields, on_error):
    for stat in fields:
        if stat.get("status") == "failed" or stat.get("role") == "geometry":
            continue
        try:
            if stat.get("role") == "fid":
                missing = feature.GetFID() < 0
            else:
                missing = not feature.IsFieldSetAndNotNull(stat["field_index"])
            if missing:
                stat["null_count"] += 1
            elif stat.get("field_type") in ("String", "WideString"):
                value = feature.GetField(stat["field_index"])
                if isinstance(value, str):
                    if value == "":
                        stat["empty_string_count"] += 1
                    elif not value.strip():
                        stat["whitespace_string_count"] += 1
        except Exception:
            # Never include the attribute value in error messages or logs.
            stat["status"] = "failed"
            on_error(stat)


def finish_stats(fields, count, complete=True):
    for stat in fields:
        if not complete or stat.get("status") == "failed":
            stat.update(null_count=None, null_rate=None, blank_string_count=None,
                        empty_string_count=None, whitespace_string_count=None,
                        blank_rate=None, reason="read_failed", status="failed")
        elif stat.get("role") == "geometry":
            stat.update(null_count=None, null_rate=None, blank_string_count=None,
                        empty_string_count=None, whitespace_string_count=None,
                        blank_rate=None, reason="geometry_not_counted")
        else:
            blank = stat["empty_string_count"] + stat["whitespace_string_count"]
            stat.update(blank_string_count=blank,
                        null_rate=stat["null_count"] / count if count else None,
                        blank_rate=(stat["null_count"] + blank) / count if count else None,
                        reason=None if count else "empty_layer")
