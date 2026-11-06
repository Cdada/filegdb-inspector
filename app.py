"""Single-user loopback HTTP service using Python's standard library."""
import argparse
import copy
import json
import secrets
import subprocess
import sys
import threading
import uuid
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from config import BASE_DIR, HOST, PORT, RUNTIME_DIR, ALLOW_MANUAL_PATH
from gdb_reader import environment, inspect_gdb, now
from gdb_scanner import find_gdbs, validate_selection
from logger_utils import create_logger


class Service:
    def __init__(self):
        self.env = environment()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.scan = None
        self.scanning = False
        self.tasks = {}
        self.active = None
        self.logger, self.log_path = create_logger()
        self.logger.info("启动环境 %s", json.dumps(self.env, ensure_ascii=False))

    def log(self, task, message):
        self.logger.info(message)
        with self.lock:
            task["logs"].append(now() + " " + message)

    def scan_folder(self, root):
        if not isinstance(root, str) or not root.strip():
            raise ValueError("请先选择目标文件夹")
        with self.lock:
            if self.active or self.scanning:
                raise ValueError("已有任务正在执行，请等待完成")
            self.scanning = True
        try:
            self.logger.info("扫描目录 %s", root)
            scan = find_gdbs(root)
            scan["scan_id"] = uuid.uuid4().hex
            with self.lock:
                self.scan = scan
            self.logger.info("扫描完成 GDB数量=%s 异常=%s", len(scan["gdbs"]), scan["errors"])
            return scan
        finally:
            with self.lock:
                self.scanning = False

    def analyze(self, payload):
        with self.lock:
            if not self.env["ready"]:
                raise ValueError("GDAL 环境不可用，请使用包含 osgeo 与 OpenFileGDB 的 Python 启动")
            if self.active or self.scanning:
                raise ValueError("已有任务正在执行，请等待完成")
            if not self.scan or payload.get("scan_id") != self.scan["scan_id"]:
                raise ValueError("扫描结果已失效，请重新扫描")
            selected = validate_selection(payload.get("paths"), self.scan)
            task_id = uuid.uuid4().hex
            task = {"task_id": task_id, "status": "running", "created_time": now(),
                    "progress": {"gdb_current": 0, "gdb_total": len(selected)},
                    "logs": deque(maxlen=300), "result": None, "error": None}
            # Keep memory bounded across repeated jobs; persisted JSON files remain available.
            while len(self.tasks) >= 10:
                del self.tasks[next(iter(self.tasks))]
            self.tasks[task_id] = task
            self.active = task_id
            scan = copy.deepcopy(self.scan)
            thread = threading.Thread(target=self.run_analysis, args=(task, selected, scan), daemon=True)
            thread.start()
            return {"task_id": task_id}

    def run_analysis(self, task, selected, scan):
        result = {"task_id": task["task_id"], "created_time": task["created_time"],
                  "gdal_version": self.env.get("gdal_version"), "environment": self.env,
                  "scan_root": scan["root"], "gdbs": [], "errors": [],
                  "null_definition": "NULL 或未设置；不含空字符串、纯空白字符串、0 或 False"}

        def progress(**values):
            with self.lock:
                task["progress"].update(values)

        try:
            self.log(task, "最终选择 " + json.dumps(selected, ensure_ascii=False))
            for index, item in enumerate(selected, 1):
                progress(gdb_current=index, gdb_name=item["name"], layer_name="",
                         layer_current=0, layer_total=0, records_read=0)
                try:
                    # Recheck immediately before opening, including resolved ancestors.
                    validate_selection([item["path"]], scan)
                except Exception as exc:
                    entry = {"code": "GDB_NOT_FOUND" if isinstance(exc, FileNotFoundError)
                             else "PERMISSION_DENIED" if isinstance(exc, PermissionError)
                             else "PATH_CHANGED", "message": str(exc), "path": item["path"]}
                    gdb = dict(item, layers=[], driver=None, status="failed", errors=[entry])
                    self.log(task, "异常 " + str(entry))
                else:
                    gdb = inspect_gdb(item, self.env, progress, lambda line: self.log(task, line))
                result["gdbs"].append(gdb)
                result["errors"].extend(gdb["errors"])
            result["finished_time"] = now()
            result["status"] = "completed_with_errors" if result["errors"] else "completed"
            folder = RUNTIME_DIR / "exports"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / (task["task_id"] + ".json")
            with output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            self.log(task, "完成。统计结果已保存 " + str(output))
            with self.lock:
                task.update(result=result, status=result["status"], export_path=str(output))
        except Exception as exc:
            self.log(task, "任务失败 " + str(exc))
            with self.lock:
                task.update(result=result, status="failed", error=str(exc))
        finally:
            with self.lock:
                self.active = None

    def task_info(self, task_id, results=False):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                raise KeyError("任务不存在；服务重启或超过十次任务后请查看 runtime/exports 留档")
            if results:
                if task["status"] == "running":
                    raise ValueError("任务尚未完成")
                return copy.deepcopy(task["result"])
            return {key: list(value) if key == "logs" else copy.deepcopy(value)
                    for key, value in task.items() if key != "result"}


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # URLs and HTTP headers (including the local token) are not logged.
            pass

        def send(self, status, data, content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; object-src 'none'")
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self):
            try:
                host = "127.0.0.1:" + str(self.server.server_port)
                if self.headers.get("Host") != host:
                    self.send(403, {"error": "仅允许通过 127.0.0.1 访问"})
                    return
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + host:
                    self.send(403, {"error": "不允许跨站请求"})
                    return
                if self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self.send(403, {"error": "不允许跨站请求"})
                    return
                path = urlsplit(self.path).path
                if path.startswith("/api/") and not secrets.compare_digest(
                        self.headers.get("X-Local-Token", ""), service.token):
                    self.send(403, {"error": "请从本地页面发起操作"})
                    return
                if self.command == "GET":
                    self.get(path)
                elif self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 2_000_000:
                        raise ValueError("请求大小无效")
                    if self.headers.get_content_type() != "application/json":
                        raise ValueError("请求必须为 JSON")
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError("请求必须是 JSON 对象")
                    if path == "/api/scan":
                        self.send(200, service.scan_folder(payload.get("root")))
                    elif path == "/api/analyze":
                        self.send(202, service.analyze(payload))
                    else:
                        self.send(404, {"error": "接口不存在"})
            except (ValueError, FileNotFoundError, PermissionError, OSError) as exc:
                self.send(400, {"error": str(exc)})
            except KeyError as exc:
                self.send(404, {"error": str(exc)})
            except Exception as exc:
                service.logger.error("服务异常 %s", exc)
                self.send(500, {"error": "服务异常，请查看运行日志"})

        def get(self, path):
            if path == "/":
                html = (BASE_DIR / "templates/index.html").read_text(encoding="utf-8")
                self.send(200, html.replace("__LOCAL_TOKEN__", service.token).encode("utf-8"), "text/html; charset=utf-8")
            elif path in ("/static/app.js", "/static/style.css"):
                mime = "text/javascript" if path.endswith(".js") else "text/css"
                self.send(200, (BASE_DIR / path.lstrip("/")).read_bytes(), mime + "; charset=utf-8")
            elif path == "/api/environment":
                self.send(200, dict(service.env, allow_manual_path=ALLOW_MANUAL_PATH,
                                    log_path=str(service.log_path), folder_picker=sys.platform == "darwin"))
            elif path == "/api/select-folder":
                if sys.platform != "darwin":
                    raise ValueError("当前系统请通过手工输入路径选择目录")
                try:
                    completed = subprocess.run([
                        "/usr/bin/osascript", "-e",
                        'POSIX path of (choose folder with prompt "请选择需要扫描的目标文件夹")'
                    ], capture_output=True, text=True, timeout=180)
                except subprocess.TimeoutExpired:
                    raise ValueError("文件夹选择超时，请重试")
                if completed.returncode:
                    if "-128" in completed.stderr:
                        self.send(200, {"cancelled": True})
                    else:
                        raise ValueError("文件夹选择器未能启动：" + completed.stderr.strip())
                else:
                    self.send(200, {"path": str(Path(completed.stdout.strip()).resolve(strict=True))})
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                if len(parts) not in (3, 4) or (len(parts) == 4 and parts[3] != "results"):
                    raise KeyError("接口不存在")
                self.send(200, service.task_info(parts[2], results=len(parts) == 4))
            else:
                self.send(404, {"error": "页面不存在"})

        do_GET = handle_request
        do_POST = handle_request

    return Handler


def open_browser(url):
    if sys.platform != "darwin":
        webbrowser.open(url)
        return
    completed = subprocess.run(["/usr/bin/open", "-a", "Google Chrome", url], capture_output=True)
    if completed.returncode:
        subprocess.run(["/usr/bin/open", url], check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    service = Service()
    print(json.dumps(service.env, ensure_ascii=False, indent=2), flush=True)
    if not service.env["ready"]:
        raise SystemExit("GDAL 检查失败：请使用包含 osgeo 与 OpenFileGDB 的 Python，macOS 可使用 start.command")
    try:
        server = ThreadingHTTPServer((HOST, PORT), make_handler(service))
    except OSError as exc:
        raise SystemExit("无法监听端口 %s：%s。请检查是否已启动，或配置 GDB_INSPECTOR_PORT。" % (PORT, exc))
    url = "http://%s:%s" % (HOST, PORT)
    print("服务已启动：" + url + "\n日志：" + str(service.log_path) + "\n按 Ctrl+C 停止。", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, open_browser, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务停止；未完成任务需重新执行。源 GDB 不受影响。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
