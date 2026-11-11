"""Loopback-only backend. Host bearer and trusted identity required on all APIs."""
from __future__ import annotations

import hmac
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
from urllib.parse import quote, unquote
from uuid import uuid4

from .store import Store, ApiError, identifier
from heater_drawing.drawing.opencadstudio import font_paths, resolve_executable
from heater_drawing.drawing.template import load_template
from heater_drawing.drawing.profile import output_template, NATIVE_PROFILE


class Handler(BaseHTTPRequestHandler):
    server_version = "HeaterDrawing/0.2.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, *_):
        pass

    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "需要明确请求长度")
        length = self.headers.get("Content-Length", "0")
        if not re.fullmatch(r"[0-9]{1,10}", length) or int(length) > limit:
            raise ApiError(413, "请求过大", "PAYLOAD_TOO_LARGE")
        value = self.rfile.read(int(length))
        if len(value) != int(length):
            raise ApiError(400, "请求内容不完整")
        return value

    def handle_api(self):
        self.connection.settimeout(30)
        request_id = uuid4().hex
        try:
            authorization = self.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization, "Bearer " + self.server.token):
                raise ApiError(401, "需要可信插件 Host", "AUTHENTICATION_REQUIRED")
            owner, session = self.headers.get("X-Heater-Owner"), self.headers.get("X-Heater-Session")
            if not identifier(owner) or not identifier(session):
                raise ApiError(401, "缺少可信会话身份", "AUTHENTICATION_REQUIRED")
            if any(c in self.path for c in ("%", "?", "\\", ".")):
                raise ApiError(400, "无效路径")
            parts = self.path.split("/")[1:]
            if parts[:3] != ["api", "heater", "v1"]:
                raise ApiError(404, "接口不存在", "NOT_FOUND")
            parts = parts[3:]
            store = self.server.store
            if self.command == "GET" and parts == ["capabilities"]:
                return self.send_json(200, {"schema_version": 1, "version": "0.2.0", "formats": ["dwg", "dxf", "pdf"],
                    "max_upload_bytes": 10 * 1024 * 1024, "template": "heater-a4-v1", "worker": "single",
                    "printing": "engineer_sample", "font_note": "TXT 使用内置替代字形", "ready": True})
            if parts == ["jobs"]:
                if self.command == "GET":
                    return self.send_json(200, {"jobs": store.listing(owner, session)})
                if self.command == "POST":
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                        raise ApiError(422, "请上传 xlsx 工作簿", "UNSUPPORTED_INPUT")
                    name = unquote(self.headers.get("X-Heater-Name", "%E5%8A%A0%E7%83%AD%E5%99%A8%E5%9B%BE%E7%BA%B8"))
                    return self.send_json(202, store.upload(owner, session, name, self.body(10 * 1024 * 1024)))
            if len(parts) >= 2 and parts[0] == "jobs" and identifier(parts[1]):
                job_id = parts[1]
                if self.command == "GET" and len(parts) == 2:
                    return self.send_json(200, store.get(job_id, owner, session))
                if self.command == "POST":
                    value = json.loads(self.body(256 * 1024))
                    if not isinstance(value, dict):
                        raise ApiError(400, "需要 JSON 对象")
                    if parts[2:] == ["decisions"]:
                        return self.send_json(202, store.decision(job_id, owner, session, value))
                    if parts[2:] == ["runs"]:
                        return self.send_json(202, store.start(job_id, owner, session, value, self.headers.get("Idempotency-Key")))
                    if len(parts) == 5 and parts[2] == "runs" and identifier(parts[3]):
                        if parts[4] == "cancel" and set(value) == {"revision_hash"}:
                            return self.send_json(200, store.cancel(job_id, parts[3], owner, session, value["revision_hash"]))
                        if parts[4] == "reviews":
                            return self.send_json(200, store.review(job_id, parts[3], owner, session, value))
                if self.command == "GET" and len(parts) == 6 and parts[2] == "runs" and parts[4] == "artifacts" and identifier(parts[3]) and identifier(parts[5]):
                    path, entry = store.artifact(job_id, parts[3], parts[5], owner, session)
                    data = path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", entry["media_type"])
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", "inline; filename*=UTF-8''" + quote(path.name))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            raise ApiError(404, "接口不存在", "NOT_FOUND")
        except ApiError as exc:
            self.send_json(exc.status, {"error": {"code": exc.code, "message": exc.message, "request_id": request_id}})
        except (ValueError, TypeError, KeyError):
            self.send_json(400, {"error": {"code": "INVALID_REQUEST", "message": "请求格式不正确", "request_id": request_id}})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_json(500, {"error": {"code": "INTERNAL_ERROR", "message": "后台处理失败，请重试", "request_id": request_id}})

    do_GET = handle_api
    do_POST = handle_api


def main():
    token, key = os.environ["HEATER_SERVICE_TOKEN"], os.environ["HEATER_RECEIPT_KEY"]
    if min(len(token), len(key)) < 40:
        raise ValueError("private_runtime_credentials_required")
    template = Path(os.environ["HEATER_TEMPLATE_DIR"])
    controlled = output_template(load_template(template), NATIVE_PROFILE)
    resolve_executable()
    font_paths(controlled)
    data = Path(os.environ["HEATER_DATA_DIR"])
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    service_lock = (data / "service.lock").open("w")
    fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    store = Store(data, template, key)
    server = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("HEATER_PORT", "0"))), Handler)
    server.daemon_threads = True
    server.store, server.token = store, token
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, shutdown)
    # Host closes this pipe on unload/exit. A child never outlives its host.
    def monitor_parent():
        sys.stdin.buffer.read()
        shutdown()
    threading.Thread(target=monitor_parent, daemon=True).start()
    print(json.dumps({"ready": True, "port": server.server_address[1], "version": "0.2.0"}), flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        store.close()
        server.server_close()


if __name__ == "__main__":
    main()
