import json
import re
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

urlopen = build_opener(ProxyHandler({})).open

import app
import logger_utils
from gdb_reader import inspect_gdb, environment
from gdb_scanner import find_gdbs, validate_selection
from statistics import tally_feature, finish_stats
from test_gdb_read import create_fixture, snapshot


class APITests(unittest.TestCase):
    def test_end_to_end_and_security(self):
        with tempfile.TemporaryDirectory(prefix="gdb api ") as temp:
            root = Path(temp).resolve()
            path = create_fixture(root)
            before = snapshot(path)
            (root / "0损坏.gdb").mkdir()
            with patch.object(logger_utils, "RUNTIME_DIR", root / "runtime"):
                service = app.Service()
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(service))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)

            def request(route, payload=None, **extra):
                headers = {"X-Local-Token": service.token, **extra}
                if payload is not None:
                    headers["Content-Type"] = "application/json"
                req = Request(base + route, data=json.dumps(payload).encode() if payload is not None else None,
                              headers=headers)
                with urlopen(req, timeout=10) as response:
                    return json.load(response)

            try:
                with urlopen(base) as response:
                    html = response.read().decode()
                self.assertIn(service.token, html)
                self.assertTrue(request("/api/environment")["ready"])
                for headers in ({"Origin": "https://example.org"}, {"Host": "evil.test"}, {"X-Local-Token": "wrong"}):
                    with self.assertRaises(HTTPError) as caught:
                        request("/api/environment", **headers)
                    self.assertEqual(caught.exception.code, 403)
                scan = request("/api/scan", {"root": str(root)})
                with self.assertRaises(HTTPError):
                    request("/api/analyze", {"scan_id": "stale", "paths": [str(path)]})
                with patch.object(app, "RUNTIME_DIR", root / "reports"):
                    task = request("/api/analyze", {"scan_id": scan["scan_id"],
                                  "paths": [item["path"] for item in scan["gdbs"]]})
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        status = request("/api/tasks/" + task["task_id"])
                        if status["status"] != "running":
                            break
                        time.sleep(.05)
                    self.assertEqual(status["status"], "completed_with_errors")
                    results = request("/api/tasks/" + task["task_id"] + "/results")
                    self.assertEqual(len(results["gdbs"]), 2)
                    self.assertEqual(results["gdbs"][0]["status"], "failed")
                    self.assertEqual(results["gdbs"][1]["status"], "success")
                    self.assertTrue(Path(status["export_path"]).exists())
                    self.assertEqual(json.loads(Path(status["export_path"]).read_text()), results)
                self.assertEqual(before, snapshot(path))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                for handler in list(service.logger.handlers):
                    handler.close()
                    service.logger.removeHandler(handler)

    def test_replaced_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "source.gdb").mkdir()
            (root / "different").mkdir()
            scan = find_gdbs(root)
            (root / "source.gdb").rmdir()
            (root / "source.gdb").symlink_to(root / "different", target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_selection([str(root / "source.gdb")], scan)

    def test_field_failure_does_not_stop_other_fields(self):
        from gdb_reader import make_field
        class Feature:
            def IsFieldSetAndNotNull(self, index):
                if index == 0:
                    raise RuntimeError("test failure")
                return True
        fields = [make_field(0, "bad", None, "Integer"), make_field(1, "good", None, "Integer")]
        errors = []
        tally_feature(Feature(), fields, errors.append)
        finish_stats(fields, 1)
        self.assertEqual(len(errors), 1)
        self.assertIsNone(fields[0]["null_count"])
        self.assertEqual(fields[1]["null_rate"], 0)

    def test_incomplete_stream_never_claims_zero_or_valid_rate(self):
        from gdb_reader import make_field
        fields = [make_field(0, "count", None, "Integer")]
        finish_stats(fields, 5, complete=False)
        self.assertIsNone(fields[0]["null_count"])
        self.assertIsNone(fields[0]["null_rate"])


if __name__ == "__main__":
    unittest.main()
