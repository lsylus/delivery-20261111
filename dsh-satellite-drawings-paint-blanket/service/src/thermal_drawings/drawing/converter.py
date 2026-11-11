"""ODA candidate adapter: local reviewed license, isolated process group, no shell.

No tested commercial success is implied by this implementation. Conversion returns
a draft only after actual DWG header AND reverse-conversion entity verification.
Independent AutoCAD reopen/edit/save acceptance is required separately.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile

from .profiles import DrawingProfile
from .validation import file_record, validate_dxf


class ConversionError(RuntimeError):
    def __init__(self, code, message, evidence=None):
        super().__init__(message)
        self.code = code
        self.evidence = evidence or {}


class DwgConverter:
    def __init__(self, config, *, inherit_worker_group=False):
        self.inherit_worker_group = inherit_worker_group
        self.config = dict(config)
        self.commands = []

    def capabilities(self):
        if self.config.get("adapter") == "opencadstudio":
            from .opencadstudio import OpenCadStudioConverter
            return OpenCadStudioConverter(self.config).capabilities()
        executable = self.config.get("executable")
        resolved = shutil.which(executable) if executable else shutil.which("ODAFileConverter")
        result = {"adapter": self.config.get("adapter"), "executable": resolved,
                  "tool_version": None, "license_state": "unverified", "status": "blocked",
                  "headless_runner": shutil.which("xvfb-run"), "real_conversion_verified": False,
                  "autocad_reopen": "not_run", "reasons": []}
        if not resolved:
            result["reasons"].append("converter_executable_missing")
        if self.config.get("adapter") != "oda_file_converter":
            result["reasons"].append("adapter_not_configured")
        if not result["headless_runner"] or os.name != "posix":
            result["reasons"].append("Linux_xvfb_run_required")
        try:
            if not resolved:
                raise ValueError("no executable")
            result["executable_record"] = file_record(resolved)
            license_ref = self.config.get("license_ref")
            if not license_ref:
                raise ValueError("no license record")
            # This is a deployment review record, never a license secret or token.
            license_data = json.loads(Path(license_ref).read_text())
            deployment = (license_data.get("decision") == "approved"
                          and license_data.get("scope") == "linux_unattended_server_conversion")
            evaluation = (license_data.get("decision") == "approved_for_evaluation"
                          and license_data.get("scope") == "b04_local_evaluation"
                          and license_data.get("user_authorization_ref"))
            required = ((deployment or evaluation)
                        and license_data.get("reviewer") and license_data.get("tool_version")
                        and license_data.get("terms_reference") and license_data.get("reviewed_at")
                        and license_data.get("executable_sha256") == result["executable_record"]["sha256"])
            if not required:
                raise ValueError("license review incomplete or executable hash mismatch")
            for tool_file in license_data.get("tool_files", []):
                if file_record(tool_file["path"])["sha256"] != tool_file["sha256"]:
                    raise ValueError("reviewed tool binary hash mismatch")
            result["license_state"] = "deployment_review_approved" if deployment else "user_authorized_evaluation_only"
            result["production_deployment_approved"] = bool(deployment)
            result["license_record"] = file_record(license_ref)
            result["tool_version"] = license_data["tool_version"]
        except (ValueError, OSError, TypeError):
            result["reasons"].append("approved_license_evidence_missing_or_mismatched")
        if not result["reasons"]:
            result["status"] = "ready_unverified"
        return result

    def _run(self, argv, timeout, cwd):
        try:
            process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       start_new_session=not self.inherit_worker_group, env={**os.environ, "QT_QPA_PLATFORM": "xcb",
                                       "XDG_CONFIG_HOME": str(Path(cwd) / "config"),
                                       "XDG_CACHE_HOME": str(Path(cwd) / "cache")})
        except OSError as exc:
            raise ConversionError("converter_start_failed", str(exc), {"argv": argv}) from exc
        timed_out = False
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(os.getpgrp() if self.inherit_worker_group else process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        finally:
            # Also reap descendants if a launcher exits leaving Qt helpers behind.
            try:
                if not self.inherit_worker_group:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        record = {"argv": argv, "exit_code": process.returncode, "timed_out": timed_out,
                  "output": output.decode("utf-8", errors="replace")}
        self.commands.append(record)
        if timed_out:
            raise ConversionError("converter_timeout", "conversion process group killed", record)
        if process.returncode:
            raise ConversionError("converter_failed", "converter exited nonzero", record)

    def convert(self, dxf, destination, profile=DrawingProfile(), *, document):
        if self.config.get("adapter") == "opencadstudio":
            from .opencadstudio import OpenCadStudioConverter
            return OpenCadStudioConverter(self.config, inherit_worker_group=self.inherit_worker_group).convert(dxf, destination, profile, document=document)
        self.commands = []
        capability = self.capabilities()
        if capability["status"] != "ready_unverified":
            raise ConversionError("capability_unavailable", "; ".join(capability["reasons"]), capability)
        if self.config.get("target_version") != profile.target_dwg_version:
            raise ConversionError("profile_mismatch", "configured target must match drawing profile")
        timeout = self.config.get("timeout_s")
        if not isinstance(timeout, int) or timeout < 1:
            raise ConversionError("invalid_timeout", "positive timeout required")
        fonts = self.config.get("font_paths", [])
        if not any(Path(p).is_file() and Path(p).name == profile.font for p in fonts):
            raise ConversionError("font_missing", "profile font file must be explicitly configured")
        dxf, destination = Path(dxf).resolve(), Path(destination).resolve()
        sidecar = destination.with_suffix(".readback.dxf")
        if destination == dxf or sidecar == dxf or destination.exists() or sidecar.exists():
            raise ConversionError("destination_exists", "destination must be new; prior outputs are preserved")
        validate_dxf(document, dxf, profile)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".dwg-", dir=destination.parent) as staging:
            root = Path(staging)
            input_dir, output_dir, reverse_dir = [root / name for name in ("input", "output", "reverse")]
            for directory in (input_dir, output_dir, reverse_dir):
                directory.mkdir()
            shutil.copyfile(dxf, input_dir / "sample.dxf")
            base = [capability["headless_runner"], "-a", capability["executable"]]
            self._run(base + [str(input_dir), str(output_dir), profile.target_dwg_version, "DWG", "0", "1", "*.dxf"], timeout, root)
            output = output_dir / "sample.dwg"
            if not output.is_file() or output.is_symlink() or output.stat().st_size <= 6 or output.read_bytes()[:6] != b"AC1032":
                raise ConversionError("invalid_dwg", "missing/non-DWG/wrong version output", {"commands": self.commands})
            self._run(base + [str(output_dir), str(reverse_dir), profile.target_dwg_version, "DXF", "0", "1", "*.dwg"], timeout, root)
            reverse = reverse_dir / "sample.dxf"
            if reverse.is_symlink():
                raise ConversionError("invalid_readback", "symlink output rejected")
            try:
                readback = validate_dxf(document, reverse, profile)
            except Exception as exc:
                raise ConversionError("invalid_readback", str(exc), {"commands": self.commands}) from exc
            # Draft candidate only. This does not register a formal C03 Artifact.
            os.link(reverse, sidecar)
            try:
                os.link(output, destination)  # Same filesystem; atomic no-clobber publication.
            except OSError:
                sidecar.unlink()
                raise
        capability.update(real_conversion_verified=True, status="verified_for_this_conversion")
        return {"status": "needs_review", "capability": capability, "commands": self.commands,
                "input": file_record(dxf), "output": file_record(destination),
                "readback": {**readback, "file": file_record(destination.with_suffix(".readback.dxf"))},
                "resources_created": [str(root)], "resources_cleaned": [str(root)],
                "autocad_reopen": "not_run", "formal_artifact_published": False}
