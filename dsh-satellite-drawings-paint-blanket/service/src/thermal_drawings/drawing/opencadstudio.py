"""Isolated OpenCADStudio export with verified saves and strict geometry readback."""
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import uuid
import ezdxf
from .converter import ConversionError
from .profiles import DrawingProfile
from .validation import file_record, validate_dxf


class NativeSession:
    def __init__(self, executable, root, timeout, *, inherit_worker_group=False):
        self.timeout = timeout
        self.calls = []
        env = dict(os.environ)
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
            folder = Path(root) / key
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            env[key] = str(folder)
        self.stderr = (Path(root) / "native-stderr.log").open("wb")
        self.own_group = not inherit_worker_group
        try:
            self.process = subprocess.Popen(
                [executable, "--serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.stderr, env=env, start_new_session=self.own_group)
            self.greeting = self._read()
            if not self.greeting.get("ready"):
                raise ConversionError("converter_start_failed", "OpenCADStudio was not ready")
        except Exception:
            self.close()
            raise

    def _read(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout):
                raise ConversionError("converter_timeout", "OpenCADStudio reply timed out")
        line = self.process.stdout.readline()
        if not line:
            raise ConversionError("converter_failed", "OpenCADStudio closed the control channel")
        try:
            return json.loads(line)
        except ValueError as exc:
            raise ConversionError("converter_protocol_error", "Invalid OpenCADStudio JSON reply") from exc

    def call(self, request):
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        self.process.stdin.flush()
        reply = self._read()
        self.calls.append({"request": request, "response": reply})
        if reply.get("ok") is not True:
            raise ConversionError("converter_request_failed", "OpenCADStudio refused an operation", reply)
        return reply

    def verified_save(self, path, fmt):
        state = self.call({"protocol": 1, "op": "state"})
        result = self.call({
            "protocol": 1, "op": "save_verified", "request_id": uuid.uuid4().hex,
            "document_id": state["document_id"], "path": str(path),
            "target_format": fmt, "target_version": "2018", "overwrite": False})
        saved = result.get("result", {})
        if (not saved.get("verified") or saved.get("target_version") != "AC1032"
                or saved.get("dropped_on_save") != 0):
            raise ConversionError("invalid_verified_save", "Save did not verify losslessly as 2018", result)
        return saved

    def close(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                process.stdin.close()
                process.wait(timeout=3)
            except (subprocess.TimeoutExpired, BrokenPipeError):
                if self.own_group:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=3)
        self.stderr.close()


def validate_opencad_readback(document, raw, normalized, profile=DrawingProfile()):
    """Retain raw bytes; normalize only diagnosed non-graphical orphan TABLESTYLE."""
    doc = ezdxf.readfile(raw)
    styles = {e.dxf.handle for e in doc.objects
              if e.dxftype() == "TABLESTYLE" and e.dxf.owner == "0"}
    audit = doc.audit()
    allowed = re.compile(r"Deleted TABLESTYLE\(#([0-9A-Fa-f]+)\) entity with invalid owner handle #0\.")
    fixes = []
    for fix in audit.fixes:
        match = allowed.fullmatch(fix.message)
        if int(fix.code) != 202 or not match or match.group(1) not in styles:
            raise ConversionError("invalid_readback", "Unexpected DXF repair",
                                  {"code": int(fix.code), "message": fix.message})
        fixes.append({"code": int(fix.code), "message": fix.message,
                      "scope": "auxiliary_readback_only"})
    if audit.errors:
        raise ConversionError("invalid_readback", "DXF audit errors",
                              {"errors": [e.message for e in audit.errors]})
    if fixes:
        doc.saveas(normalized)
        result = validate_dxf(document, normalized, profile)
    else:
        result = validate_dxf(document, raw, profile)
    return {**result, "raw_file": file_record(raw), "auxiliary_normalization": fixes,
            "dwg_modified": False, "raw_audit_fixes": len(fixes)}


class OpenCadStudioConverter:
    def __init__(self, config, *, inherit_worker_group=False):
        self.config = dict(config)
        self.inherit_worker_group = inherit_worker_group

    def capabilities(self):
        executable = self.config.get("executable")
        resolved = shutil.which(executable) if executable else shutil.which("OpenCADStudio")
        reasons = []
        if not resolved:
            reasons.append("converter_executable_missing")
        elif Path(resolved).open("rb").read(2) == b"#!":
            reasons.append("native_binary_required_for_profile_isolation")
        return {"adapter": "opencadstudio", "executable": resolved,
                "status": "blocked" if reasons else "ready_unverified",
                "reasons": reasons, "tool_version": None,
                "license_state": "installed_official_application",
                "real_conversion_verified": False, "autocad_reopen": "not_run"}

    def convert(self, dxf, destination, profile=DrawingProfile(), *, document):
        capability = self.capabilities()
        if capability["status"] != "ready_unverified":
            raise ConversionError("capability_unavailable", "; ".join(capability["reasons"]), capability)
        if self.config.get("target_version") != profile.target_dwg_version:
            raise ConversionError("profile_mismatch", "Configured target must match drawing profile")
        timeout = self.config.get("timeout_s")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
            raise ConversionError("invalid_timeout", "Positive timeout required")
        if not any(Path(p).is_file() and Path(p).name == profile.font for p in self.config.get("font_paths", [])):
            raise ConversionError("font_missing", "Profile font file must be explicitly configured")
        dxf, destination = Path(dxf).resolve(), Path(destination).resolve()
        raw_sidecar = destination.with_suffix(".readback.dxf")
        normalized_sidecar = destination.with_suffix(".readback.validated.dxf")
        targets = (destination, raw_sidecar, normalized_sidecar)
        if dxf in targets or any(p.exists() for p in targets):
            raise ConversionError("destination_exists", "Destination must be new; prior outputs are preserved")
        validate_dxf(document, dxf, profile)
        destination.parent.mkdir(parents=True, exist_ok=True)
        published = []
        with tempfile.TemporaryDirectory(prefix=".opencad-", dir=destination.parent) as staging:
            root = Path(staging)
            output, raw, normalized = (root / name for name in ("drawing.dwg", "readback.dxf", "validated.dxf"))
            session = NativeSession(capability["executable"], root, timeout,
                                    inherit_worker_group=self.inherit_worker_group)
            try:
                session.call({"op": "open", "path": str(dxf)})
                saved = session.verified_save(output, "dwg")
                if output.is_symlink() or output.read_bytes()[:6] != b"AC1032":
                    raise ConversionError("invalid_dwg", "Missing DWG 2018 output")
                session.call({"op": "open", "path": str(output)})
                reopened = session.call({"protocol": 1, "op": "state"})
                if reopened.get("missing_fonts"):
                    raise ConversionError("font_missing", "OpenCADStudio reports missing fonts", reopened["missing_fonts"])
                reverse_saved = session.verified_save(raw, "dxf")
                readback = validate_opencad_readback(document, raw, normalized, profile)
                version = session.greeting["version"]
                commands = session.calls
            finally:
                session.close()
            try:
                for src, target in ((raw, raw_sidecar), (normalized, normalized_sidecar), (output, destination)):
                    if src.exists():
                        os.link(src, target)
                        published.append(target)
            except OSError:
                for path in published:
                    path.unlink()
                raise
        readback["raw_file"] = file_record(raw_sidecar)
        readback["file"] = file_record(normalized_sidecar if normalized_sidecar.exists() else raw_sidecar)
        capability.update(tool_version=version, real_conversion_verified=True, status="verified_for_this_conversion")
        return {"status": "needs_review", "capability": capability, "commands": commands,
                "input": file_record(dxf), "output": file_record(destination), "readback": readback,
                "opencadstudio_save_verified": saved, "opencadstudio_reverse_verified": reverse_saved,
                "opencadstudio_reopen": {"passed": True, "missing_fonts": reopened.get("missing_fonts", [])},
                "resources_created": [str(root)], "resources_cleaned": [str(root)],
                "autocad_reopen": "not_run", "formal_artifact_published": False}
