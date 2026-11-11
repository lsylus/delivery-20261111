"""Render an existing DWG in an isolated real OpenCADStudio GUI via official MCP.

Usage: .venv/bin/python scripts/opencad_preview.py drawing.dwg preview.png
       --config deploy/opencadstudio-5090.json
Requires Linux xvfb-run and the installed native application, no shared GUI profile.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import sys
import tempfile
import time
import uuid

from .validation import file_record

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "thermal-drawing-preview", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {"extensions": {"io.modelcontextprotocol/tasks": {}}},
}


class Client:
    def __init__(self, executable, log, timeout=45, *, inherit_worker_group=False):
        self.own_group = not inherit_worker_group
        self.timeout = timeout
        self.serial = 0
        self.process = subprocess.Popen(
            [executable, "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, start_new_session=self.own_group)

    def rpc(self, method, params):
        self.serial += 1
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": self.serial,
                                             "method": method, "params": params}) + "\n").encode())
        self.process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout):
                raise RuntimeError("OpenCADStudio MCP timed out")
        response = json.loads(self.process.stdout.readline())
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def call(self, name, arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments, "_meta": META})
        deadline = time.monotonic() + self.timeout
        while result.get("resultType") == "task":
            task_id = result["taskId"]
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError("OpenCADStudio task timed out")
                time.sleep(0.1)
                task = self.rpc("tasks/get", {"taskId": task_id, "_meta": META})
                if task["status"] in ("failed", "cancelled"):
                    raise RuntimeError(task["status"])
                if task["status"] == "completed":
                    result = task["result"]
                    break
        data = result.get("structuredContent")
        if data is not None and data.get("ok") is False:
            raise RuntimeError(data)
        return data if data is not None else result

    def close(self):
        descendants = child_processes(self.process.pid)
        try:
            self.process.stdin.close()
            self.process.wait(timeout=3)
        except (subprocess.TimeoutExpired, BrokenPipeError):
            pass
        try:
            if self.own_group:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            # GUI children can outlive MCP EOF. Wait until they cannot write
            # profile files before the isolated temporary profile is removed.
            terminate_processes(descendants)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self.process.stdout.close()


def child_processes(parent):
    # Linux-owned child tree only; never inspect or terminate shared editor sessions.
    found = []
    children = Path(f"/proc/{parent}/task/{parent}/children")
    try:
        pids = [int(value) for value in children.read_text().split()]
    except (OSError, ValueError):
        return found
    for pid in pids:
        found.extend(child_processes(pid))
        found.append(pid)
    return found


def process_identity(pid):
    try:
        # comm can contain spaces or parentheses; fields after its last ')' start
        # with state (field 3), and starttime is field 22. Zombies cannot write.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def terminate_processes(pids, *, timeout=3):
    owned = {pid: process_identity(pid) for pid in pids}
    owned = {pid: identity for pid, identity in owned.items() if identity is not None}
    def remaining():
        return [pid for pid, identity in owned.items() if process_identity(pid) == identity]
    for termination_signal in (signal.SIGTERM, signal.SIGKILL):
        for pid in remaining():
            try:
                os.kill(pid, termination_signal)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout
        while remaining() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not remaining():
            return
    raise RuntimeError("Owned OpenCADStudio subprocesses did not exit")


def render(args):
    source, destination = Path(args.drawing).resolve(), Path(args.png).resolve()
    if not source.is_file() or source.read_bytes()[:6] != b"AC1032":
        raise ValueError("Expected a real DWG 2018 input")
    if destination.exists():
        raise ValueError("Preview destination already exists")
    config = json.loads(Path(args.config).read_text())["dwg"]
    executable = config["executable"]
    if Path(executable).open("rb").read(2) == b"#!":
        raise ValueError("Use the native binary, which respects isolated profile paths")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".opencad-preview-") as temporary:
        root = Path(temporary)
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
            path = root / key
            path.mkdir(mode=0o700)
            os.environ[key] = str(path)
        os.environ.update(LIBGL_ALWAYS_SOFTWARE="1", WGPU_BACKEND="vulkan",
                          VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/lvp_icd.x86_64.json")
        with (root / "mcp-stderr.log").open("wb") as log:
            client = Client(executable, log, inherit_worker_group=args.inherit_worker_group)
            try:
                sessions = client.call("ocs_sessions", {"launch_if_none": True})["result"]
                if len(sessions) != 1:
                    raise RuntimeError("Expected exactly one isolated editor")
                session_id = sessions[0]["session_id"]
                common = {"ocs_session_id": session_id}
                for _ in range(6):
                    sessions = client.call("ocs_sessions", {"launch_if_none": False})["result"]
                    if not sessions[0].get("modal"):
                        break
                    client.call("ocs_execute", {**common, "request": {
                        "op": "action", "name": "close_modal", "request_id": uuid.uuid4().hex}})
                if sessions[0].get("modal"):
                    raise RuntimeError("Startup modal did not close")
                client.call("ocs_open", {**common, "path": str(source)})
                if args.background != "current":
                    client.call("ocs_run", {**common, "command": "BACKGROUND " + args.background})
                state = client.call("ocs_read", {**common, "op": "state"})
                audit = client.call("ocs_read", {**common, "op": "audit", "parameters": {
                    "target_format": "dwg", "target_version": "2018"}})
                text = client.call("ocs_read", {**common, "op": "text_audit"})
                text_records = client.call("ocs_read", {**common, "op": "records", "parameters": {
                    "collection": "entities", "type": "Text"}})
                bounds = audit.get("bounds")
                frame = {}
                if bounds and bounds.get("min") and bounds.get("max"):
                    low, high = bounds["min"], bounds["max"]
                    pad = max(high[0]-low[0], high[1]-low[1], 1) * 0.08
                    frame = {"view": "region", "bounds": [low[0]-pad, low[1]-pad, high[0]+pad, high[1]+pad]}
                if args.bounds:
                    frame = {"view": "region", "bounds": args.bounds}
                capture = client.rpc("tools/call", {
                    "name": "ocs_render", "arguments": {**common, **frame, "max_dimension": 1600}, "_meta": META})
                block = next(b for b in capture["content"] if b["type"] == "image")
                png = base64.b64decode(block["data"], validate=True)
                if png[:8] != b"\x89PNG\r\n\x1a\n":
                    raise RuntimeError("MCP did not produce PNG bytes")
                destination.write_bytes(png)
                width, height = struct.unpack(">II", png[16:24])
                report = {
                    "ok": True, "backend": "OpenCADStudio real GUI via official MCP",
                    "version": state.get("version"), "input": file_record(source),
                    "display_background": args.background, "display_frame": frame,
                    "preview": {**file_record(destination), "width": width, "height": height},
                    "missing_fonts": state.get("missing_fonts", []),
                    "audit": audit, "text_audit": text, "text_records": text_records,
                    "limitations": ["CPU software renderer may include the application GPU notice",
                                    "Preview is application viewport capture, not independent CAD acceptance"],
                }
                destination.with_suffix(".preview.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
                print(json.dumps({"ok": True, "png": str(destination), "width": width, "height": height}))
            finally:
                client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drawing")
    parser.add_argument("png")
    parser.add_argument("--config", default=str(Path.cwd() / "deploy/opencadstudio-5090.json"))
    parser.add_argument("--background", choices=["current", "White", "LightGray", "Black"], default="White")
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"))
    parser.add_argument("--inherit-worker-group", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--inside-display", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.inside_display:
        command = ["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24 -nolisten tcp",
                   sys.executable, "-m", "thermal_drawings.drawing.opencad_preview", args.drawing, args.png,
                   "--config", args.config, "--inside-display"]
        command += ["--background", args.background]
        if args.bounds:
            command += ["--bounds", *map(str, args.bounds)]
        if args.inherit_worker_group:
            command += ["--inherit-worker-group"]
        process = subprocess.Popen(command)
        try:
            if process.wait(timeout=120):
                raise RuntimeError("OpenCADStudio preview process failed")
        finally:
            if process.poll() is None:
                terminate_processes(child_processes(process.pid))
                process.terminate()
                process.wait(timeout=3)
    else:
        render(args)

def render_export_preview(dwg, destination, config_path, revision_id, *, timeout=150):
    """Best-effort renderer in the worker's process group; verified DWG stays intact."""
    dwg, destination = Path(dwg).resolve(), Path(destination).resolve()
    source = file_record(dwg)
    command = [sys.executable, "-m", "thermal_drawings.drawing.opencad_preview",
               str(dwg), str(destination), "--config", str(Path(config_path).resolve()),
               "--inherit-worker-group", "--background", "White"]
    process = None
    report_path = destination.with_suffix(".preview.json")
    if destination.exists() or report_path.exists():
        return {"status": "unavailable", "source_dwg_sha256": source["sha256"],
                "revision_id": revision_id, "reason": "Preview destination already exists",
                "backend": "opencadstudio"}
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_processes(child_processes(process.pid))
            process.terminate()
            process.communicate(timeout=3)
            raise RuntimeError("OpenCADStudio preview timed out")
        if process.returncode:
            raise RuntimeError("OpenCADStudio preview process failed")
        report = json.loads(report_path.read_text())
        if (not report.get("ok") or report["input"]["sha256"] != source["sha256"]
                or report["preview"]["sha256"] != file_record(destination)["sha256"]
                or destination.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("OpenCADStudio preview/source binding failed")
        report["revision_id"] = revision_id
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return {"status": "ready", "source_dwg_sha256": source["sha256"],
                "revision_id": revision_id, "file": file_record(destination),
                "report": file_record(report_path), "backend": "opencadstudio"}
    except Exception as error:
        # Remove only partial outputs of this invocation, preserving the verified DWG.
        for path in (destination, report_path):
            path.unlink(missing_ok=True)
        return {"status": "unavailable", "source_dwg_sha256": source["sha256"],
                "revision_id": revision_id, "reason": str(error), "backend": "opencadstudio"}


if __name__ == "__main__":
    main()
