"""Disabled-by-default DWG command adapter with explicit evidence states."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any, Sequence

import ezdxf


_RUNTIME_EXECUTION_PROVENANCE: dict[object, str] = {}


def _runtime_digest(record: dict[str, Any]) -> str:
    canonical = {key: value for key, value in record.items() if key != "_runtime_provenance"}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _seal_runtime_record(record: dict[str, Any]) -> None:
    token = object()
    record["_runtime_provenance"] = token
    _RUNTIME_EXECUTION_PROVENANCE[token] = _runtime_digest(record)


def _runtime_provenance_error(record: dict[str, Any], label: str) -> str | None:
    token = record.get("_runtime_provenance")
    expected = _RUNTIME_EXECUTION_PROVENANCE.get(token)
    if expected is None:
        return f"imported {label} record has no trusted runtime provenance"
    if _runtime_digest(record) != expected:
        return f"{label} record changed after the controlled execution"
    descriptor = _artifact(record.get("record"))
    if descriptor is None or descriptor[0].suffix.lower() != ".json":
        return f"{label} record descriptor changed after the controlled execution"
    return None


class ConversionError(RuntimeError):
    def __init__(self, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.evidence = evidence or {}


@dataclass(frozen=True)
class Capability:
    state: str
    converter: str | None
    converter_sha256: str | None
    license_scope: str
    target: str
    detail: str
    verified_dwg: dict[str, str] | None = None
    verified_roundtrip_dxf: dict[str, str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unverified(converter: Path, detail: str, scope: str = "project_evaluation_only") -> Capability:
    return Capability("available_unverified", str(converter), _sha256(converter), scope, "ACAD2018", detail)


def _artifact(record: object) -> tuple[Path, str] | None:
    if not isinstance(record, dict):
        return None
    path = Path(str(record.get("path", "")))
    digest = str(record.get("sha256", ""))
    if not path.is_file() or len(digest) != 64 or digest != _sha256(path):
        return None
    return path.resolve(), digest


def _dwg_payload_error(path: Path) -> str | None:
    if not path.is_file():
        return "DWG output is missing"
    content = path.read_bytes()
    if not content.startswith(b"AC1032"):
        return "DWG output is not an ACAD2018 DWG"
    if len(content) < 1024:
        return "DWG output is header-only or otherwise not substantive"
    sample = content[6: min(len(content), 65542)]
    counts = {value: sample.count(value) for value in set(sample)}
    entropy = -sum(
        (count / len(sample)) * math.log2(count / len(sample))
        for count in counts.values()
    )
    if len(counts) < 16 or entropy < 3.5:
        return "DWG output is a synthetic or header-padded DWG payload (low entropy)"
    return "DWG structure is unverified because no trusted DWG parser/readback is configured"


def _controlled_execution_record(item: dict[str, Any], label: str) -> tuple[dict[str, Any] | None, str | None]:
    artifact = _artifact(item.get("record"))
    if artifact is None or artifact[0].suffix.lower() != ".json":
        return None, f"{label} command lacks a controlled execution record"
    try:
        record = json.loads(artifact[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, f"{label} controlled execution record is invalid JSON"
    if record.get("schema_version") != 2 or record.get("record_kind") != "heater_drawing.controlled_execution":
        return None, f"{label} command record schema is not the current controlled helper schema"
    return record, None


def _timing_error(record: dict[str, Any], label: str) -> str | None:
    names = (
        "started_wall_ns",
        "finished_wall_ns",
        "started_monotonic_ns",
        "finished_monotonic_ns",
    )
    if any(not isinstance(record.get(name), int) for name in names):
        return f"{label} record lacks complete wall/monotonic timing"
    wall_elapsed = record["finished_wall_ns"] - record["started_wall_ns"]
    monotonic_elapsed = record["finished_monotonic_ns"] - record["started_monotonic_ns"]
    if wall_elapsed < 0 or monotonic_elapsed < 0:
        return f"{label} record timing is inverted"
    allowed_drift = max(5_000_000_000, monotonic_elapsed // 4)
    if abs(wall_elapsed - monotonic_elapsed) > allowed_drift:
        return f"{label} wall and monotonic durations are inconsistent"
    now_ns = time.time_ns()
    if record["finished_wall_ns"] > now_ns + 300_000_000_000:
        return f"{label} record finish time is implausibly in the future"
    return None


def _runtime_execution_error(
    record: dict[str, Any],
    converter: Path,
    source: tuple[Path, str] | None,
    output: tuple[Path, str],
    output_type: str,
    *,
    require_runtime_provenance: bool,
) -> str | None:
    if record.get("schema_version") != 2 or record.get("record_kind") != "heater_drawing.controlled_execution":
        return "command record schema is not the current controlled helper schema"
    if require_runtime_provenance:
        provenance_error = _runtime_provenance_error(record, "command")
        if provenance_error:
            return provenance_error
    if (
        record.get("status") != "passed"
        or record.get("exit_code") != 0
        or record.get("executable_path") != str(converter.resolve())
        or record.get("executable_sha256") != _sha256(converter)
        or record.get("output_format") != output_type
        or not isinstance(record.get("process_pid"), int)
        or record["process_pid"] <= 0
    ):
        return "command execution identity/status fields are invalid"
    timing_error = _timing_error(record, "command execution")
    if timing_error:
        return timing_error
    if source is not None:
        source_record = record.get("input")
        try:
            current_source_sha256 = _sha256(source[0])
            current_source_size = source[0].stat().st_size
        except OSError:
            return "command record is not bound to the exact current runtime input bytes"
        if (
            not isinstance(source_record, dict)
            or source_record.get("path") != str(source[0])
            or source_record.get("sha256") != source[1]
            or source[1] != current_source_sha256
            or source_record.get("sha256") != current_source_sha256
            or source_record.get("size") != current_source_size
        ):
            return "command record is not bound to the exact current runtime input bytes"
    output_record = record.get("output")
    try:
        current_output_sha256 = _sha256(output[0])
        current_output_size = output[0].stat().st_size
    except OSError:
        return "command record is not bound to the exact current runtime output bytes"
    if (
        not isinstance(output_record, dict)
        or output_record.get("path") != str(output[0])
        or output_record.get("sha256") != output[1]
        or output[1] != current_output_sha256
        or output_record.get("sha256") != current_output_sha256
        or output_record.get("size") != current_output_size
    ):
        return "command record is not bound to the exact current runtime output bytes"
    logs = []
    for stream in ("stdout", "stderr"):
        artifact = _artifact(record.get(stream))
        if artifact is None:
            return f"command record lacks a complete raw {stream} log"
        logs.append(artifact[0].read_bytes())
    if not any(logs):
        return "command record raw logs are both empty"
    return None


def _runtime_version_error(
    record: dict[str, Any],
    converter: Path,
    *,
    require_runtime_provenance: bool,
) -> str | None:
    if require_runtime_provenance:
        provenance_error = _runtime_provenance_error(record, "converter version")
        if provenance_error:
            return provenance_error
    if (
        record.get("schema_version") != 2
        or record.get("record_kind") != "heater_drawing.controlled_version_execution"
        or record.get("argv") != [str(converter.resolve()), "--version"]
        or record.get("status") != "passed"
        or record.get("exit_code") != 0
        or record.get("executable_path") != str(converter.resolve())
        or record.get("executable_sha256") != _sha256(converter)
        or not isinstance(record.get("process_pid"), int)
        or record["process_pid"] <= 0
    ):
        return "converter version execution identity/status fields are invalid"
    timing_error = _timing_error(record, "converter version execution")
    if timing_error:
        return timing_error
    for stream in ("stdout", "stderr"):
        if _artifact(record.get(stream)) is None:
            return f"converter version execution lacks a complete raw {stream} log"
    return None


def _normal(value: object) -> object:
    if hasattr(value, "x") and hasattr(value, "y"):
        return [round(float(value.x), 6), round(float(value.y), 6), round(float(getattr(value, "z", 0.0)), 6)]
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _normal(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normal(item) for item in value]
    return str(value)


def _xdata(entity) -> list[str]:
    try:
        return [str(value) for code, value in entity.get_xdata("HEATER_DRAWING") if code == 1000]
    except ezdxf.DXFValueError:
        return []


def _entity_signature(entity) -> dict[str, Any]:
    kind = entity.dxftype()
    signature: dict[str, Any] = {"type": kind, "layer": entity.dxf.get("layer", "0"), "xdata": _xdata(entity)}
    if kind == "LINE":
        signature.update(start=_normal(entity.dxf.start), end=_normal(entity.dxf.end))
    elif kind == "LWPOLYLINE":
        signature.update(points=_normal(list(entity.get_points("xyseb"))), closed=bool(entity.closed))
    elif kind == "TEXT":
        signature.update(
            text=entity.dxf.text, insert=_normal(entity.dxf.insert), align_point=_normal(entity.dxf.get("align_point", (0, 0, 0))),
            height=_normal(entity.dxf.height), rotation=_normal(entity.dxf.get("rotation", 0.0)), style=entity.dxf.style,
            width=_normal(entity.dxf.get("width", 1.0)), halign=int(entity.dxf.get("halign", 0)), valign=int(entity.dxf.get("valign", 0)),
        )
    elif kind == "MTEXT":
        signature.update(
            text=entity.plain_text(), insert=_normal(entity.dxf.insert), height=_normal(entity.dxf.char_height),
            rotation=_normal(entity.dxf.get("rotation", 0.0)), style=entity.dxf.style,
            attachment=int(entity.dxf.get("attachment_point", 1)),
        )
    elif kind == "DIMENSION":
        virtual = [_entity_signature(item) for item in entity.virtual_entities() if item.dxftype() != "POINT"]
        signature.update(
            dimstyle=entity.dxf.get("dimstyle", ""), text=entity.dxf.get("text", ""),
            measurement=round(float(entity.get_measurement()), 6), defpoint=_normal(entity.dxf.defpoint),
            defpoint2=_normal(entity.dxf.get("defpoint2", (0, 0, 0))), defpoint3=_normal(entity.dxf.get("defpoint3", (0, 0, 0))),
            text_midpoint=_normal(entity.dxf.get("text_midpoint", (0, 0, 0))), virtual=virtual,
        )
    elif kind == "INSERT":
        signature.update(name=entity.dxf.name, insert=_normal(entity.dxf.insert), rotation=_normal(entity.dxf.get("rotation", 0.0)), xscale=_normal(entity.dxf.get("xscale", 1.0)), yscale=_normal(entity.dxf.get("yscale", 1.0)))
    elif kind == "SOLID":
        signature["vertices"] = [_normal(entity.dxf.get(name)) for name in ("vtx0", "vtx1", "vtx2", "vtx3")]
    else:
        attributes = dict(entity.dxf.all_existing_dxf_attribs())
        for name in ("handle", "owner", "geometry"):
            attributes.pop(name, None)
        signature["attributes"] = _normal(attributes)
    return signature


def _table_record_signature(record) -> dict[str, Any]:
    attributes = dict(record.dxf.all_existing_dxf_attribs())
    for name in ("handle", "owner"):
        attributes.pop(name, None)
    return _normal(attributes)  # type: ignore[return-value]


def _audited_dxf_signature(path: Path) -> dict[str, Any]:
    try:
        document = ezdxf.readfile(path)
        auditor = document.audit()
    except (OSError, ezdxf.DXFError) as exc:
        raise ConversionError(f"invalid DXF evidence {path}: {exc}") from exc
    if auditor.has_errors:
        raise ConversionError(f"DXF evidence has audit errors: {path}")
    entities = [_entity_signature(entity) for entity in document.modelspace()]
    if not entities:
        raise ConversionError(f"DXF evidence has no modelspace entities: {path}")
    entities.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    layouts = []
    for layout in document.layouts:
        viewports = [_entity_signature(item) for item in layout.query("VIEWPORT")]
        viewports.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        layouts.append({
            "name": layout.name,
            "paper": _normal({name: layout.dxf.get(name) for name in (
                "paper_width", "paper_height", "plot_rotation", "plot_paper_units",
                "left_margin", "right_margin", "top_margin", "bottom_margin",
            )}),
            "viewports": viewports,
        })
    return {
        "dxf_version": document.dxfversion,
        "insunits": int(document.header.get("$INSUNITS", 0)),
        "layers": sorted([_table_record_signature(layer) for layer in document.layers], key=lambda item: str(item)),
        "styles": sorted([_table_record_signature(style) for style in document.styles], key=lambda item: str(item)),
        "dimstyles": sorted([_table_record_signature(style) for style in document.dimstyles], key=lambda item: str(item)),
        "entities": entities,
        "layouts": sorted(layouts, key=lambda item: item["name"]),
    }


def _command_evidence(
    item: object,
    converter: Path,
    source: tuple[Path, str],
    output: tuple[Path, str],
    label: str,
) -> str | None:
    if not isinstance(item, dict):
        return f"missing {label} command evidence"
    controlled, controlled_error = _controlled_execution_record(item, label)
    if controlled_error:
        return controlled_error
    assert controlled is not None
    argv = controlled.get("argv")
    if not isinstance(argv, list) or not argv or Path(str(argv[0])).resolve() != converter.resolve():
        return f"{label} argv is not bound to the exact converter"
    output_type = "DWG" if label == "forward" else "DXF"
    expected_prefix = [
        str(converter), str(source[0].parent), str(output[0].parent),
        "ACAD2018", output_type,
    ]
    if argv[:5] != expected_prefix or len(argv) not in {7, 8}:
        return f"{label} argv does not use the fixed ODA folder/version/type contract"
    if str(argv[5]) not in {"0", "1"} or str(argv[6]) != "1":
        return f"{label} argv recurse/audit flags are invalid"
    if len(argv) == 8 and str(argv[7]) != source[0].name:
        return f"{label} argv input filter does not bind the exact input file"
    summary_fields = {
        "argv": argv,
        "exit_code": controlled.get("exit_code"),
        "input_path": controlled.get("input", {}).get("path") if isinstance(controlled.get("input"), dict) else None,
        "input_sha256": controlled.get("input", {}).get("sha256") if isinstance(controlled.get("input"), dict) else None,
        "output_path": controlled.get("output", {}).get("path") if isinstance(controlled.get("output"), dict) else None,
        "output_sha256": controlled.get("output", {}).get("sha256") if isinstance(controlled.get("output"), dict) else None,
        "stdout": controlled.get("stdout"),
        "stderr": controlled.get("stderr"),
    }
    if any(item.get(name) != value for name, value in summary_fields.items()):
        return f"{label} outer command summary does not match its controlled execution record"
    error = _runtime_execution_error(
        controlled,
        converter,
        source,
        output,
        output_type,
        require_runtime_provenance=False,
    )
    if error:
        return f"{label} {error}"
    return f"{label} imported command record has no trusted runtime provenance"


def _trusted_executable_error(converter: Path) -> str | None:
    if os.name != "nt":
        return "ELF converter identity lacks a code-trusted vendor signature or digest"
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $env:HEATER_SIGNATURE_TARGET;"
        "[pscustomobject]@{Status=[string]$s.Status;"
        "Subject=[string]$s.SignerCertificate.Subject;"
        "Issuer=[string]$s.SignerCertificate.Issuer}|ConvertTo-Json -Compress"
    )
    try:
        environment = dict(os.environ)
        environment["HEATER_SIGNATURE_TARGET"] = str(converter)
        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=environment,
        )
        signature = json.loads(process.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return f"cannot verify converter Authenticode identity: {exc}"
    identity = f"{signature.get('Subject', '')} {signature.get('Issuer', '')}".lower()
    if process.returncode != 0 or signature.get("Status") != "Valid" or "open design alliance" not in identity:
        return "converter lacks a valid Open Design Alliance Authenticode identity"
    return None


def _version_execution_error(receipt: dict[str, Any], converter: Path) -> str | None:
    artifact = _artifact(receipt.get("record"))
    if artifact is None:
        return "converter version receipt lacks a controlled execution record"
    try:
        controlled = json.loads(artifact[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "converter version controlled execution record is invalid JSON"
    if controlled.get("stdout") != receipt.get("stdout") or controlled.get("stderr") != receipt.get("stderr"):
        return "converter version receipt does not match its controlled execution record"
    error = _runtime_version_error(
        controlled,
        converter,
        require_runtime_provenance=False,
    )
    if error:
        return error
    return "imported converter version record has no trusted runtime provenance"


def _validate_converter_identity(converter: Path, record: dict[str, Any]) -> str | None:
    if converter.name.lower() not in {"odafileconverter", "odafileconverter.exe"}:
        return "authorized executable name is not ODAFileConverter"
    header = converter.read_bytes()[:4]
    if not (header.startswith(b"MZ") or header == b"\x7fELF"):
        return "authorized converter is not a native PE/ELF executable"
    trust_error = _trusted_executable_error(converter)
    if trust_error:
        return trust_error
    receipt_artifact = _artifact(record.get("version_receipt"))
    if receipt_artifact is None or receipt_artifact[0].suffix.lower() != ".json":
        return "converter version receipt is missing or invalid"
    try:
        receipt = json.loads(receipt_artifact[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "converter version receipt is not valid JSON"
    if (
        receipt.get("product") != "ODA File Converter"
        or receipt.get("version") != record.get("version")
        or receipt.get("executable_path") != str(converter)
        or receipt.get("executable_sha256") != _sha256(converter)
        or receipt.get("argv") != [str(converter), "--version"]
        or receipt.get("exit_code") != 0
    ):
        return "converter version receipt is not bound to the executable/product/version"
    stdout = _artifact(receipt.get("stdout"))
    stderr = _artifact(receipt.get("stderr"))
    if stdout is None or stderr is None:
        return "converter version receipt lacks complete logs"
    execution_error = _version_execution_error(receipt, converter)
    if execution_error:
        return execution_error
    version_output = stdout[0].read_text(encoding="utf-8", errors="replace") + stderr[0].read_text(encoding="utf-8", errors="replace")
    if "ODA File Converter" not in version_output or str(record.get("version")) not in version_output:
        return "converter version output does not identify ODA File Converter and its version"
    return None


def capabilities(converter: Path | None, license_record: Path | None) -> Capability:
    if converter is None or not converter.is_file():
        return Capability("not_configured", None, None, "none_for_this_project", "ACAD2018", "no project-configured converter")
    converter = converter.resolve()
    if license_record is None or not license_record.is_file():
        return _unverified(converter, "converter exists but project license record is missing", "unconfirmed_for_this_project")
    try:
        record = json.loads(license_record.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConversionError(f"invalid license record: {exc}") from exc
    if record.get("project") != "heater-drawing" or record.get("evaluation_authorized") is not True:
        return _unverified(converter, "license record does not authorize this project", "not_authorized_for_this_project")
    converter_record = record.get("converter")
    if not isinstance(converter_record, dict):
        return _unverified(converter, "authorization does not identify the converter product and version")
    if converter_record.get("product") != "ODA File Converter" or not isinstance(converter_record.get("version"), str) or not converter_record["version"].strip():
        return _unverified(converter, "converter product/version is not explicitly recognized")
    if converter_record.get("path") != str(converter) or converter_record.get("sha256") != _sha256(converter):
        return _unverified(converter, "converter path/hash does not match the authorized executable")
    identity_error = _validate_converter_identity(converter, converter_record)
    if identity_error:
        return _unverified(converter, identity_error)
    operator = record.get("operator")
    performed_at = record.get("performed_at")
    try:
        performed = datetime.fromisoformat(str(performed_at).replace("Z", "+00:00"))
    except ValueError:
        performed = None
    now = datetime.now(timezone.utc)
    if (
        not isinstance(operator, dict)
        or not all(isinstance(operator.get(name), str) and operator[name].strip() for name in ("id", "name"))
        or performed is None
        or performed.tzinfo is None
        or performed > now + timedelta(minutes=5)
        or performed < now - timedelta(days=365)
    ):
        return _unverified(converter, "round-trip operator/time evidence is missing, future, or stale")
    evidence = record.get("round_trip_evidence")
    if not isinstance(evidence, dict):
        return _unverified(converter, "authorization exists but no stored round-trip evidence")
    artifacts: dict[str, tuple[Path, str]] = {}
    for key in ("input", "dwg", "roundtrip_dxf"):
        artifact = _artifact(evidence.get(key))
        if artifact is None:
            return _unverified(converter, f"round-trip evidence is incomplete or has a hash mismatch: {key}")
        artifacts[key] = artifact
    dwg = artifacts["dwg"][0]
    payload_error = _dwg_payload_error(dwg)
    if payload_error:
        return _unverified(converter, f"stored DWG is invalid: {payload_error}")
    commands = evidence.get("commands")
    if not isinstance(commands, dict):
        return _unverified(converter, "round-trip evidence lacks forward/reverse command bindings")
    for label, source_key, output_key in (("forward", "input", "dwg"), ("reverse", "dwg", "roundtrip_dxf")):
        error = _command_evidence(commands.get(label), converter, artifacts[source_key], artifacts[output_key], label)
        if error:
            return _unverified(converter, error)
    try:
        before = _audited_dxf_signature(artifacts["input"][0])
        after = _audited_dxf_signature(artifacts["roundtrip_dxf"][0])
    except ConversionError as exc:
        return _unverified(converter, str(exc))
    if before != after:
        return _unverified(converter, "round-trip DXF semantic signature differs from the exact input")
    return Capability(
        "verified_evaluation_only", str(converter), _sha256(converter), "project_evaluation_only", "ACAD2018",
        "recognized converter, exact commands, complete logs, and audited semantic round-trip verified; production remains disabled",
        {"path": str(artifacts["dwg"][0]), "sha256": artifacts["dwg"][1]},
        {"path": str(artifacts["roundtrip_dxf"][0]), "sha256": artifacts["roundtrip_dxf"][1]},
    )


def _write_log(path: Path, content: str) -> dict[str, str]:
    path.write_text(content, encoding="utf-8")
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def _bound_artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def run_fixed_command(
    executable: Path,
    arguments: Sequence[str],
    expected_output: Path,
    timeout: float,
    evidence_dir: Path | None = None,
    expected_format: str = "DWG",
    expected_input: Path | None = None,
) -> dict[str, Any]:
    evidence_dir = (evidence_dir or expected_output.parent / "conversion-logs").resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(time.time_ns())
    stdout_path = evidence_dir / f"{run_id}.stdout.log"
    stderr_path = evidence_dir / f"{run_id}.stderr.log"
    metadata_path = evidence_dir / f"{run_id}.json"
    argv = [str(executable.resolve()), *arguments]
    expected_output = expected_output.resolve()
    expected_input = expected_input.resolve() if expected_input is not None else None
    input_record = _bound_artifact(expected_input) if expected_input is not None and expected_input.is_file() else None
    started_wall_ns = time.time_ns()
    started_monotonic_ns = time.monotonic_ns()
    stdout = ""
    stderr = ""
    status = "not_started"
    exit_code: int | None = None
    process_pid: int | None = None
    error_message: str | None = None
    expected_format = expected_format.upper()
    try:
        if expected_format not in {"DWG", "DXF"}:
            raise ConversionError(f"unsupported converter output format: {expected_format}")
        if not executable.is_file():
            raise ConversionError("converter executable is missing")
        if expected_input is not None and input_record is None:
            raise ConversionError("exact converter input is missing")
        if expected_output.exists():
            raise ConversionError("expected output already exists; stale output is forbidden")
        popen_kwargs: dict[str, Any] = {
            "cwd": str(evidence_dir), "shell": False, "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE, "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **popen_kwargs)
        process_pid = process.pid
        status = "running"
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            partial_stdout, partial_stderr = _text(exc.stdout), _text(exc.stderr)
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            remaining_stdout, remaining_stderr = process.communicate()
            stdout = partial_stdout + _text(remaining_stdout)[len(partial_stdout):]
            stderr = partial_stderr + _text(remaining_stderr)[len(partial_stderr):]
            exit_code = process.returncode
            status = "timeout"
            raise ConversionError(f"converter timed out after {timeout:g}s") from exc
        exit_code = process.returncode
        if exit_code != 0:
            status = "failed"
            raise ConversionError(f"converter exited {exit_code}")
        if not expected_output.is_file():
            status = "invalid_output"
            raise ConversionError("converter exited 0 but did not create a substantive output file")
        if expected_output.stat().st_mtime_ns < started_wall_ns:
            status = "invalid_output"
            raise ConversionError("converter output is stale")
        if expected_format == "DWG":
            payload_error = _dwg_payload_error(expected_output)
            if payload_error:
                status = "invalid_output"
                raise ConversionError(payload_error)
        else:
            try:
                _audited_dxf_signature(expected_output)
            except ConversionError as exc:
                status = "invalid_output"
                raise ConversionError(f"converter output is not a substantive audited DXF: {exc}") from exc
        status = "passed"
    except ConversionError as exc:
        error_message = str(exc)
    stdout_record = _write_log(stdout_path, stdout)
    stderr_record = _write_log(stderr_path, stderr)
    finished_wall_ns = time.time_ns()
    finished_monotonic_ns = time.monotonic_ns()
    output_record = _bound_artifact(expected_output) if expected_output.is_file() else None
    evidence: dict[str, Any] = {
        "schema_version": 2, "record_kind": "heater_drawing.controlled_execution",
        "argv": argv, "status": status, "exit_code": exit_code,
        "executable_path": str(executable.resolve()),
        "executable_sha256": _sha256(executable) if executable.is_file() else None,
        "process_pid": process_pid, "output_format": expected_format,
        "started_wall_ns": started_wall_ns,
        "finished_wall_ns": finished_wall_ns,
        "started_monotonic_ns": started_monotonic_ns,
        "finished_monotonic_ns": finished_monotonic_ns,
        "stdout": stdout_record, "stderr": stderr_record,
        "input": input_record,
        "output": output_record,
    }
    if error_message is not None:
        evidence["error"] = error_message
    metadata_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["record"] = {"path": str(metadata_path), "sha256": _sha256(metadata_path)}
    if error_message is not None:
        raise ConversionError(error_message, evidence)
    _seal_runtime_record(evidence)
    return evidence


def run_version_command(
    executable: Path,
    timeout: float,
    evidence_dir: Path,
) -> dict[str, Any]:
    evidence_dir = evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(time.time_ns())
    stdout_path = evidence_dir / f"{run_id}.version.stdout.log"
    stderr_path = evidence_dir / f"{run_id}.version.stderr.log"
    metadata_path = evidence_dir / f"{run_id}.version.json"
    argv = [str(executable.resolve()), "--version"]
    started_wall_ns = time.time_ns()
    started_monotonic_ns = time.monotonic_ns()
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    process_pid: int | None = None
    status = "not_started"
    error_message: str | None = None
    try:
        if not executable.is_file():
            raise ConversionError("converter executable is missing")
        popen_kwargs: dict[str, Any] = {
            "cwd": str(evidence_dir), "shell": False, "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE, "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **popen_kwargs)
        process_pid = process.pid
        status = "running"
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            exit_code = process.returncode
            status = "timeout"
            raise ConversionError(f"converter version command timed out after {timeout:g}s") from exc
        exit_code = process.returncode
        if exit_code != 0:
            status = "failed"
            raise ConversionError(f"converter version command exited {exit_code}")
        if "ODA File Converter" not in (stdout + stderr):
            status = "invalid_output"
            raise ConversionError("converter version output does not identify ODA File Converter")
        status = "passed"
    except ConversionError as exc:
        error_message = str(exc)
    stdout_record = _write_log(stdout_path, stdout)
    stderr_record = _write_log(stderr_path, stderr)
    finished_wall_ns = time.time_ns()
    finished_monotonic_ns = time.monotonic_ns()
    evidence: dict[str, Any] = {
        "schema_version": 2,
        "record_kind": "heater_drawing.controlled_version_execution",
        "argv": argv,
        "status": status,
        "exit_code": exit_code,
        "executable_path": str(executable.resolve()),
        "executable_sha256": _sha256(executable) if executable.is_file() else None,
        "process_pid": process_pid,
        "started_wall_ns": started_wall_ns,
        "finished_wall_ns": finished_wall_ns,
        "started_monotonic_ns": started_monotonic_ns,
        "finished_monotonic_ns": finished_monotonic_ns,
        "stdout": stdout_record,
        "stderr": stderr_record,
    }
    if error_message is not None:
        evidence["error"] = error_message
    metadata_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["record"] = {"path": str(metadata_path), "sha256": _sha256(metadata_path)}
    if error_message is not None:
        raise ConversionError(error_message, evidence)
    _seal_runtime_record(evidence)
    return evidence
