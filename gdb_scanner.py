"""Discover FileGDB directories without following symlinks or entering a GDB."""
import os
from pathlib import Path


def find_gdbs(root_dir):
    root = Path(root_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("目标路径必须是文件夹")
    found, errors = [], []

    def add(path):
        found.append({"path": str(path), "directory": str(path.parent), "name": path.name})

    def onerror(exc):
        errors.append({"code": "PERMISSION_DENIED" if isinstance(exc, PermissionError)
                       else "SCAN_FAILED", "path": exc.filename, "message": str(exc)})

    if root.name.lower().endswith(".gdb"):
        add(root)
    else:
        for current, dirs, _ in os.walk(root, followlinks=False, onerror=onerror):
            descend = []
            for name in sorted(dirs):
                path = Path(current) / name
                if path.is_symlink():
                    continue
                if name.lower().endswith(".gdb"):
                    add(path)
                else:
                    descend.append(name)
            dirs[:] = descend
    found.sort(key=lambda item: item["path"].casefold())
    for index, item in enumerate(found, 1):
        item["gdb_index"] = index
    return {"root": str(root), "gdbs": found, "errors": errors}


def validate_selection(paths, scan):
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("请选择至少一个扫描得到的 GDB")
    known = {item["path"]: item for item in scan["gdbs"]}
    root = Path(scan["root"])
    selected = []
    for raw in dict.fromkeys(paths):
        if raw not in known:
            raise ValueError("只能读取本次扫描得到的 GDB")
        path = Path(raw)
        resolved = path.resolve(strict=True)
        if (path.is_symlink() or resolved != path or not path.is_dir()
                or path.suffix.lower() != ".gdb"
                or (resolved != root and root not in resolved.parents)):
            raise ValueError("GDB 路径已变化或超出扫描范围：" + raw)
        selected.append(dict(known[raw]))
    return sorted(selected, key=lambda item: item["gdb_index"])
