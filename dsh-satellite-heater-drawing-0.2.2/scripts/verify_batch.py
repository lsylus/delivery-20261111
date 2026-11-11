#!/usr/bin/env python3
"""Run allow-listed Batch acceptance commands and write C07 evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evidence_common import file_sha256, source_contract_sha256
from check_source_boundary import compare_snapshots, snapshot_hash, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts" / "acceptance_registry.json"
BATCH_PATTERN = re.compile(r"^B[0-9]{2}$")
PYTEST_PASSED = re.compile(r"(?:^|\s)([0-9]+) passed(?:,| in|$)")
PYTEST_SKIPPED = re.compile(r"(?:^|\s)([0-9]+) skipped(?:,| in|$)")
PYTEST_FAILED = re.compile(r"(?:^|[\s,])([0-9]+) failed(?:,| in|$)")
PYTEST_ERRORS = re.compile(r"(?:^|[\s,])([0-9]+) errors?(?:,| in| during|$)")
PYTEST_ABORTED = re.compile(
    r"^(?:INTERNALERROR>|!+\s*(?:Interrupted:|KeyboardInterrupt\b|(?:_pytest\.outcomes\.)?Exit:))",
    re.MULTILINE,
)
ENVIRONMENT_ERRORS = (
    "No module named ",
    "ModuleNotFoundError:",
    "ImportError: cannot import name",
)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNAVAILABLE"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_summary(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def classify_pytest(
    exit_code: int,
    output: str,
    *,
    required: bool,
) -> tuple[str, str]:
    if exit_code != 0:
        if any(marker in output for marker in ENVIRONMENT_ERRORS):
            return "blocked", f"pytest environment unavailable (exit {exit_code})"
        return "failed", f"pytest exited {exit_code}"
    failed = sum(int(value) for value in PYTEST_FAILED.findall(output))
    errors = sum(int(value) for value in PYTEST_ERRORS.findall(output))
    if failed or errors:
        return "failed", f"pytest log reports {failed} failed and {errors} errors"
    if PYTEST_ABORTED.search(output):
        return "failed", "pytest log reports an abort or internal error"
    passed = sum(int(value) for value in PYTEST_PASSED.findall(output))
    skipped = sum(int(value) for value in PYTEST_SKIPPED.findall(output))
    if passed == 0:
        reason = "zero tests passed" if skipped == 0 else f"all tests skipped ({skipped})"
        return "failed", reason
    if skipped:
        if required:
            return "failed", f"{skipped} required tests skipped"
        return "skipped", f"{passed} tests passed; {skipped} optional tests skipped"
    return "passed", f"{passed} tests passed; 0 skipped"


def classify_command_result(
    command: dict[str, Any],
    exit_code: int,
    output: str,
) -> tuple[str, str]:
    """Classify command evidence from the registry contract and actual log."""

    required = command.get("required", True)
    if command.get("kind") == "pytest":
        return classify_pytest(exit_code, output, required=required)
    if exit_code in command.get("expected_exit_codes", [0]):
        return "passed", f"command exited with expected code {exit_code}"
    if exit_code in command.get("blocked_exit_codes", []):
        return "blocked", f"required environment unavailable (exit {exit_code})"
    if any(marker in output for marker in ENVIRONMENT_ERRORS):
        return "blocked", f"required package unavailable (exit {exit_code})"
    return "failed", f"command exited {exit_code}"


def initial_summary(batch: str) -> dict[str, Any]:
    dirty = git_output("status", "--porcelain=v1")
    return {
        "batch": batch,
        "status": "blocked",
        "source_git_head": git_output("rev-parse", "HEAD"),
        "source_git_branch": git_output("branch", "--show-current"),
        "source_contract_sha256": source_contract_sha256(ROOT),
        "dirty_files": [] if not dirty else dirty.splitlines(),
        "contract_version": "1",
        "dependency_reports": {},
        "commands": [],
        "checks": [],
        "input_hashes": {},
        "artifact_hashes": {},
        "human_decisions": [],
        "blockers": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def add_check(
    summary: dict[str, Any],
    check_id: str,
    status: str,
    detail: str,
) -> None:
    summary["checks"].append(
        {"id": check_id, "status": status, "detail": detail}
    )
    if status != "passed":
        summary["blockers"].append(f"{check_id}: {detail}")


def validate_registry(
    summary: dict[str, Any],
    spec: Any,
) -> tuple[bool, bool]:
    if not isinstance(spec, dict):
        add_check(summary, "registry", "failed", "batch registry entry must be an object")
        return True, False
    commands = spec.get("commands")
    if not isinstance(commands, list) or not commands:
        add_check(summary, "registry", "failed", "commands must be a non-empty list")
        return True, False
    ids: set[str] = set()
    required_count = 0
    for command in commands:
        if not isinstance(command, dict):
            add_check(summary, "registry", "failed", "command entry must be an object")
            return True, False
        command_id = command.get("id")
        argv = command.get("argv")
        if (
            not isinstance(command_id, str)
            or not command_id
            or command_id in ids
            or not isinstance(argv, list)
            or not argv
            or not all(isinstance(part, str) and part for part in argv)
        ):
            add_check(
                summary,
                "registry",
                "failed",
                "command ids must be unique and argv must be a non-empty string list",
            )
            return True, False
        expected_exit_codes = command.get("expected_exit_codes", [0])
        if (
            not isinstance(expected_exit_codes, list)
            or not expected_exit_codes
            or any(type(value) is not int or value < 0 for value in expected_exit_codes)
            or len(expected_exit_codes) != len(set(expected_exit_codes))
        ):
            add_check(
                summary,
                "registry",
                "failed",
                "expected_exit_codes must be a non-empty unique list of non-negative integers",
            )
            return True, False
        if command.get("kind") == "pytest" and expected_exit_codes != [0]:
            add_check(
                summary,
                "registry",
                "failed",
                "pytest commands must expect only exit code 0",
            )
            return True, False
        ids.add(command_id)
        if command.get("required", True):
            required_count += 1
    if required_count == 0:
        add_check(summary, "registry", "failed", "at least one command must be required")
        return True, False
    add_check(
        summary,
        "registry",
        "passed",
        f"{len(commands)} commands registered; {required_count} required",
    )
    return False, False


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is missing")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return timestamp.astimezone(timezone.utc)


def resolve_project_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("evidence path escapes project root")
    return path


def validate_evidence_hashes(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"dependency {field} must be a hash mapping")
    verified: dict[str, str] = {}
    for relative, expected_hash in value.items():
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ValueError(f"dependency {field} contains an invalid entry")
        path = resolve_project_path(relative)
        if not path.is_file():
            raise FileNotFoundError(relative)
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"dependency evidence hash changed: {relative}")
        verified[relative] = actual_hash
    return verified


def _tracked_head_bytes(path: Path) -> bytes:
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    prefix = git_output("rev-parse", "--show-prefix")
    if prefix == "UNAVAILABLE":
        raise ValueError("cannot resolve Git path for dependency acceptance binding")
    git_path = f"{prefix}{relative}"
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{git_path}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("dependency acceptance binding is not tracked at current HEAD")
    return result.stdout


def _validate_current_b01_contract(
    dependency: dict[str, Any], report: dict[str, Any], report_hash: str
) -> dict[str, Any]:
    binding_path = resolve_project_path(dependency["acceptance_binding_path"])
    if binding_path.read_bytes() != _tracked_head_bytes(binding_path):
        raise ValueError("dependency acceptance binding differs from the current Git HEAD blob")
    binding = load_json(binding_path)
    if (
        binding.get("schema_version") != 1
        or binding.get("batch") != "B01"
        or binding.get("report_path") != dependency["path"]
        or binding.get("report_sha256") != report_hash
        or binding.get("source_contract_sha256") != report.get("source_contract_sha256")
        or binding.get("source_git_head") != report.get("source_git_head")
    ):
        raise ValueError("dependency acceptance binding does not identify the exact B01 report/source")
    registry = load_json(REGISTRY)
    b01 = registry.get("batches", {}).get("B01", {})
    expected_commands = b01.get("commands")
    actual_commands = report.get("commands")
    if not isinstance(expected_commands, list) or not isinstance(actual_commands, list):
        raise ValueError("B01 command contract is unavailable")
    if len(expected_commands) != len(actual_commands):
        raise ValueError("B01 dependency command count differs from the registry")
    command_contract = []
    for expected, actual in zip(expected_commands, actual_commands, strict=True):
        expected_argv = [
            str(actual["argv"][0]) if part == "{python}" else part
            for part in expected["argv"]
        ]
        if expected["argv"][0] == "{python}" and Path(str(actual["argv"][0])).resolve() != Path(sys.executable).resolve():
            raise ValueError(f"B01 dependency interpreter drift: {expected['id']}")
        contract_item = {
            "id": expected["id"],
            "argv": expected["argv"],
            "required": expected.get("required", True),
            "kind": expected.get("kind"),
        }
        if (
            actual.get("id") != expected["id"]
            or actual.get("required", True) != expected.get("required", True)
            or actual.get("argv") != expected_argv
        ):
            raise ValueError(f"B01 dependency command contract drift: {expected['id']}")
        command_contract.append(contract_item)
    if binding.get("commands") != command_contract:
        raise ValueError("B01 acceptance binding command contract differs from the registry")
    check_ids = [item.get("id") for item in report.get("checks", [])]
    if check_ids != binding.get("required_checks") or len(check_ids) != len(set(check_ids)):
        raise ValueError("B01 dependency required check set/order is incomplete")
    input_paths = sorted(report.get("input_hashes", {}))
    artifact_paths = sorted(report.get("artifact_hashes", {}))
    if input_paths != binding.get("input_paths") or artifact_paths != binding.get("artifact_paths"):
        raise ValueError("B01 dependency input/artifact set is incomplete")
    boundary = b01.get("boundary_evidence", {})
    expected_boundary = sorted([boundary.get("path"), boundary.get("baseline_path")])
    if binding.get("boundary_inputs") != expected_boundary or not set(expected_boundary).issubset(input_paths):
        raise ValueError("B01 dependency boundary inputs are incomplete")
    historical = dependency.get("historical_accepted_report")
    if binding.get("historical_accepted_report") != historical:
        raise ValueError("B01 acceptance binding changed the historical accepted fact")
    return {
        "path": dependency["acceptance_binding_path"],
        "sha256": file_sha256(binding_path),
    }


def validate_dependency_reports(
    summary: dict[str, Any],
    dependencies: Any,
    registry: dict[str, Any] | None = None,
) -> tuple[bool, bool]:
    if registry is None:
        registry = load_json(REGISTRY)
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list):
        add_check(
            summary,
            "dependency-reports",
            "failed",
            "dependency_reports must be a list",
        )
        return True, False
    blocked = False
    now = datetime.now(timezone.utc)
    for index, dependency in enumerate(dependencies):
        check_id = f"dependency-{index}"
        if not isinstance(dependency, dict):
            add_check(
                summary,
                check_id,
                "blocked",
                "dependency must bind path, hash, status, source, contract, and age",
            )
            blocked = True
            continue
        try:
            path = resolve_project_path(dependency["path"])
            if not path.is_file():
                raise FileNotFoundError(dependency["path"])
            actual_hash = file_sha256(path)
            report = load_json(path)
            verification = dependency.get("verification", "immutable_hash")
            if verification == "immutable_hash":
                if actual_hash != dependency["sha256"]:
                    raise ValueError("dependency report content hash changed")
                expected_source_contract = dependency.get("source_contract_sha256")
            elif verification == "current_source_contract":
                if "sha256" in dependency or "source_contract_sha256" in dependency:
                    raise ValueError("current-source dependency must not embed a self-referential report/source hash")
                expected_source_contract = summary["source_contract_sha256"]
            else:
                raise ValueError("dependency verification mode is invalid")
            if report.get("batch") != dependency.get("batch"):
                raise ValueError("dependency batch does not match registry")
            if report.get("status") != "passed":
                raise ValueError(
                    f"dependency status is {report.get('status')!r}, not passed"
                )
            if report.get("contract_version") != dependency.get(
                "contract_version"
            ):
                raise ValueError("dependency contract version mismatch")
            if verification == "immutable_hash" and report.get("source_git_head") != dependency.get("source_git_head"):
                raise ValueError("dependency source Git version mismatch")
            if report.get("source_contract_sha256") != expected_source_contract:
                raise ValueError("dependency source content fingerprint mismatch")
            if (
                not isinstance(report.get("source_contract_sha256"), str)
                or re.fullmatch(
                    r"[0-9a-f]{64}", report["source_contract_sha256"]
                )
                is None
            ):
                raise ValueError("dependency source content fingerprint is invalid")
            age = now - parse_timestamp(report.get("timestamp"))
            max_age_hours = float(dependency.get("max_age_hours", 24 * 365))
            if age.total_seconds() < 0 or age.total_seconds() > max_age_hours * 3600:
                raise ValueError("dependency report is stale")
            commands = report.get("commands")
            checks = report.get("checks")
            if not isinstance(commands, list) or not commands:
                raise ValueError("dependency command evidence is incomplete")
            producer = registry.get("batches", {}).get(dependency.get("batch"))
            producer_commands = producer.get("commands") if isinstance(producer, dict) else None
            if not isinstance(producer_commands, list) or not producer_commands:
                raise ValueError("dependency producer command contract is unavailable")
            expected_command_ids = [item.get("id") for item in producer_commands]
            reported_command_ids = [
                item.get("id") if isinstance(item, dict) else None
                for item in commands
            ]
            if len(reported_command_ids) != len(expected_command_ids):
                raise ValueError("dependency command count differs from the producer registry")
            if reported_command_ids != expected_command_ids:
                raise ValueError("dependency command set/order does not match the producer registry")
            command_ids: set[str] = set()
            verified_logs: dict[str, str] = {}
            for item, command_contract in zip(commands, producer_commands, strict=True):
                if not isinstance(item, dict):
                    raise ValueError("dependency command evidence is incomplete")
                command_id = item.get("id")
                if (
                    not isinstance(command_id, str)
                    or not command_id
                    or command_id in command_ids
                ):
                    raise ValueError("dependency command ids are invalid")
                command_ids.add(command_id)
                required = item.get("required", True)
                if type(required) is not bool:
                    raise ValueError("dependency command required flag is invalid")
                if required != command_contract.get("required", True):
                    raise ValueError("dependency command required flag does not match the producer registry")
                exit_code = item.get("exit_code")
                if type(exit_code) is not int:
                    raise ValueError("dependency command exit code is invalid")
                log_relative = item.get("log")
                log_hash = item.get("log_sha256")
                if not isinstance(log_relative, str) or not isinstance(log_hash, str):
                    raise ValueError("dependency command log evidence is incomplete")
                log_path = resolve_project_path(log_relative)
                if not log_path.is_file():
                    raise FileNotFoundError(log_relative)
                actual_log_hash = file_sha256(log_path)
                if actual_log_hash != log_hash:
                    raise ValueError(f"dependency command log changed: {log_relative}")
                recomputed_status, _ = classify_command_result(
                    command_contract, exit_code, log_path.read_text(encoding="utf-8")
                )
                if item.get("status") != recomputed_status:
                    raise ValueError(
                        f"dependency command status contradicts exit/log evidence: {command_id}"
                    )
                if required and recomputed_status != "passed":
                    raise ValueError("dependency command evidence is incomplete")
                if not required and recomputed_status not in {"passed", "skipped", "blocked"}:
                    raise ValueError("dependency optional command evidence is invalid")
                verified_logs[log_relative] = actual_log_hash
            if (
                not isinstance(checks, list)
                or not checks
                or any(
                    not isinstance(item, dict) or item.get("status") != "passed"
                    for item in checks
                )
            ):
                raise ValueError("dependency checks are incomplete")
            if report.get("blockers"):
                raise ValueError("dependency report still contains blockers")
            verified_inputs = validate_evidence_hashes(
                report.get("input_hashes"), "input_hashes"
            )
            verified_artifacts = validate_evidence_hashes(
                report.get("artifact_hashes"), "artifact_hashes"
            )
            binding_info = None
            if verification == "current_source_contract" and dependency.get("batch") == "B01":
                binding_info = _validate_current_b01_contract(dependency, report, actual_hash)
            summary["dependency_reports"][dependency["path"]] = {
                "sha256": actual_hash,
                "verification": verification,
                "batch": report["batch"],
                "source_git_head": report["source_git_head"],
                "source_contract_sha256": report["source_contract_sha256"],
                "contract_version": report["contract_version"],
                "timestamp": report["timestamp"],
                "verified_logs": verified_logs,
                "verified_inputs": verified_inputs,
                "verified_artifacts": verified_artifacts,
            }
            if binding_info is not None:
                summary["dependency_reports"][dependency["path"]]["acceptance_binding"] = binding_info
            historical = dependency.get("historical_accepted_report")
            if historical is not None:
                if not isinstance(historical, dict):
                    raise ValueError("historical accepted dependency binding is invalid")
                historical_path = resolve_project_path(historical["path"])
                historical_hash = file_sha256(historical_path)
                historical_report = load_json(historical_path)
                if historical_hash != historical.get("sha256") or historical_report.get("batch") != dependency.get("batch") or historical_report.get("status") != "passed":
                    raise ValueError("historical accepted dependency fact changed")
                summary["dependency_reports"][dependency["path"]]["historical_accepted_report"] = {
                    "path": historical["path"], "sha256": historical_hash
                }
            add_check(summary, check_id, "passed", "dependency evidence is valid")
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            add_check(summary, check_id, "blocked", str(exc))
            blocked = True
    if not dependencies:
        add_check(summary, "dependency-reports", "passed", "no B01 dependencies")
    return False, blocked


def validate_human_gates(
    summary: dict[str, Any],
    gates: Any,
) -> tuple[bool, bool]:
    if gates is None:
        gates = []
    if not isinstance(gates, list):
        add_check(summary, "human-gates", "failed", "human_gates must be a list")
        return True, False
    blocked = False
    for index, gate in enumerate(gates):
        check_id = f"human-gate-{index}"
        try:
            if not isinstance(gate, dict):
                raise ValueError("human gate requires structured evidence")
            path = resolve_project_path(gate["evidence_path"])
            if not path.is_file():
                raise FileNotFoundError(gate["evidence_path"])
            actual_hash = file_sha256(path)
            if actual_hash != gate["sha256"]:
                raise ValueError("human evidence hash changed")
            evidence = load_json(path)
            if evidence.get("status") != "approved":
                raise ValueError("human gate is not approved")
            for field in ("actor", "decided_at", "scope", "artifact_hashes"):
                if not evidence.get(field):
                    raise ValueError(f"human evidence lacks {field}")
            summary["human_decisions"].append(
                {"path": gate["evidence_path"], "sha256": actual_hash}
            )
            add_check(summary, check_id, "passed", "human gate evidence is valid")
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            add_check(summary, check_id, "blocked", str(exc))
            blocked = True
    if not gates:
        add_check(summary, "human-gates", "passed", "no B01 human gates")
    return False, blocked


def validate_boundary_evidence(
    summary: dict[str, Any],
    spec: Any,
) -> tuple[bool, bool]:
    if spec is None:
        return False, False
    try:
        if not isinstance(spec, dict):
            raise ValueError("boundary_evidence must be an object")
        path = resolve_project_path(spec["path"])
        if not path.is_file():
            raise FileNotFoundError(spec["path"])
        baseline_path = resolve_project_path(spec["baseline_path"])
        if not baseline_path.is_file():
            raise FileNotFoundError(spec["baseline_path"])
        evidence = load_json(path)
        baseline = load_json(baseline_path)
        validate_snapshot(baseline)
        validate_snapshot(evidence, allow_comparison=True)
        if evidence.get("mode") != "comparison":
            raise ValueError("boundary evidence must compare before and after")
        comparison = evidence.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("status") not in {
            "unchanged",
            "changes_observed",
        }:
            raise ValueError("boundary comparison is incomplete")
        actual_baseline_hash = snapshot_hash(baseline)
        if evidence.get("baseline_sha256") != actual_baseline_hash:
            raise ValueError("boundary baseline hash does not match registered baseline")
        if evidence.get("reference_root") != baseline.get("reference_root"):
            raise ValueError("boundary comparison uses a different reference root")
        if evidence.get("project_source_sha256") != summary[
            "source_contract_sha256"
        ]:
            raise ValueError("boundary evidence does not match current B01 source")
        if baseline.get("project_source_sha256") != summary[
            "source_contract_sha256"
        ]:
            raise ValueError("boundary baseline does not match current B01 source")
        checked_at = parse_timestamp(evidence.get("checked_at"))
        baseline_checked_at = parse_timestamp(baseline.get("checked_at"))
        if baseline_checked_at > checked_at:
            raise ValueError("boundary baseline is newer than comparison")
        age = datetime.now(timezone.utc) - checked_at
        baseline_age = datetime.now(timezone.utc) - baseline_checked_at
        max_age_hours = float(spec.get("max_age_hours", 24))
        if (
            age.total_seconds() < 0
            or age.total_seconds() > max_age_hours * 3600
            or baseline_age.total_seconds() < 0
            or baseline_age.total_seconds() > max_age_hours * 3600
        ):
            raise ValueError("boundary evidence is stale")
        expected_comparison = compare_snapshots(baseline, evidence)
        if comparison != expected_comparison:
            raise ValueError("boundary comparison conclusion does not match snapshots")
        summary["input_hashes"][spec["path"]] = file_sha256(path)
        summary["input_hashes"][spec["baseline_path"]] = file_sha256(
            baseline_path
        )
        add_check(
            summary,
            "source-boundary",
            "passed",
            f"valid comparison; {comparison['status']}",
        )
        return False, False
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        add_check(summary, "source-boundary", "blocked", str(exc))
        return False, True


def fixture_checks() -> tuple[list[dict[str, Any]], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    source = load_json(ROOT / "docs/reference/source-files.json")
    manifest = load_json(ROOT / "fixtures/case/manifest.json")
    source_files = {item["name"]: item for item in source["files"]}
    fixture_files = {item["name"]: item for item in manifest["files"]}
    ok = source_files == fixture_files and len(source_files) == 10
    for name, expected in source_files.items():
        path = ROOT / "fixtures/case" / name
        actual_hash = file_sha256(path) if path.is_file() else None
        actual_bytes = path.stat().st_size if path.is_file() else None
        hashes[f"fixtures/case/{name}"] = actual_hash or "missing"
        ok = (
            ok
            and actual_hash == expected["sha256"]
            and actual_bytes == expected["bytes"]
        )
    checks.append(
        {
            "id": "source-fixtures",
            "status": "passed" if ok else "failed",
            "detail": "10 immutable originals match source-files and manifest",
        }
    )
    expected = load_json(ROOT / "fixtures/case/expected.json")
    rows = expected.get("rows", [])
    expected_ok = (
        len(rows) == 3
        and rows[1].get("excel_row") == 3
        and rows[1].get("standards_reviewer") == "郑玲"
    )
    checks.append(
        {
            "id": "expected-case",
            "status": "passed" if expected_ok else "failed",
            "detail": "expected has exactly 3 rows and Excel O3=郑玲",
        }
    )
    return checks, hashes


def resolved_openapi_routes(document: dict[str, Any]) -> set[str]:
    routes: set[str] = set()
    global_servers = document.get("servers", [{"url": ""}])
    for path, item in document["paths"].items():
        operation_servers: list[dict[str, str]] | None = None
        for method in ("get", "post", "put", "patch", "delete"):
            operation = item.get(method)
            if operation and "servers" in operation:
                operation_servers = operation["servers"]
                break
        servers = operation_servers or item.get("servers") or global_servers
        for server in servers:
            base = server["url"].rstrip("/")
            routes.add(f"{base}{path}")
    return routes


def foundation_checks() -> tuple[list[dict[str, Any]], dict[str, str]]:
    from heater_drawing.domain.models import SCHEMA_MODELS, schema_snapshot

    checks: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}
    schemas_ok = True
    for name in SCHEMA_MODELS:
        path = ROOT / "schemas" / name
        schemas_ok = (
            schemas_ok
            and path.is_file()
            and load_json(path) == schema_snapshot(name)
        )
        if path.is_file():
            artifacts[f"schemas/{name}"] = file_sha256(path)
    checks.append(
        {
            "id": "schema-snapshots",
            "status": "passed" if schemas_ok else "failed",
            "detail": "checked-in schemas match structural/semantic snapshots",
        }
    )

    openapi = ROOT / "schemas/openapi.json"
    lock = ROOT / "service/uv.lock"
    wheel_candidates = sorted(
        (ROOT / "dist").glob("heater_drawing_service-*.whl")
    )
    files_ok = (
        openapi.is_file()
        and lock.is_file()
        and (ROOT / "README.md").is_file()
        and len(wheel_candidates) == 1
    )
    checks.append(
        {
            "id": "foundation-files",
            "status": "passed" if files_ok else "failed",
            "detail": "lock, OpenAPI, README, and exactly one wheel exist",
        }
    )
    for path in (openapi, lock):
        if path.is_file():
            artifacts[str(path.relative_to(ROOT))] = file_sha256(path)

    wheel_ok = False
    if len(wheel_candidates) == 1:
        wheel = wheel_candidates[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        wheel_ok = {
            "heater_drawing/__init__.py",
            "heater_drawing/config.py",
            "heater_drawing/domain/models.py",
        }.issubset(names)
        artifacts[str(wheel.relative_to(ROOT))] = file_sha256(wheel)
    checks.append(
        {
            "id": "wheel-contents",
            "status": "passed" if wheel_ok else "failed",
            "detail": "wheel contains package, models, and resource locator",
        }
    )

    openapi_ok = False
    if openapi.is_file():
        routes = resolved_openapi_routes(load_json(openapi))
        expected = {
            "/healthz",
            "/readyz",
            "/api/heater/v1/capabilities",
            "/api/heater/v1/jobs",
            "/api/heater/v1/jobs/{job_id}",
            "/api/heater/v1/jobs/{job_id}/decisions",
            "/api/heater/v1/jobs/{job_id}/runs",
            "/api/heater/v1/jobs/{job_id}/runs/{run_id}",
            "/api/heater/v1/jobs/{job_id}/runs/{run_id}/cancel",
            "/api/heater/v1/jobs/{job_id}/runs/{run_id}/retry",
            "/api/heater/v1/jobs/{job_id}/runs/{run_id}/artifacts",
            "/api/heater/v1/artifacts/{artifact_id}/content",
            "/api/heater/v1/jobs/{job_id}/runs/{run_id}/reviews",
        }
        openapi_ok = routes == expected
    checks.append(
        {
            "id": "openapi-routes",
            "status": "passed" if openapi_ok else "failed",
            "detail": "health routes are unprefixed and business routes use /api/heater/v1",
        }
    )
    return checks, artifacts


def registered_format_evidence(spec: dict[str, Any]) -> Path:
    commands = [
        command
        for command in spec.get("commands", [])
        if isinstance(command, dict) and command.get("id") == "check-format-gate"
    ]
    if len(commands) != 1:
        raise ValueError("format evidence requires exactly one check-format-gate command")
    argv = commands[0].get("argv")
    if not isinstance(argv, list) or argv.count("--evidence") != 1:
        raise ValueError("check-format-gate must declare one --evidence path")
    index = argv.index("--evidence")
    if index + 1 >= len(argv) or not isinstance(argv[index + 1], str):
        raise ValueError("check-format-gate --evidence path is missing")
    evidence = resolve_project_path(argv[index + 1])
    evidence_root = (ROOT / "docs/evidence").resolve()
    if not evidence.is_relative_to(evidence_root) or evidence == evidence_root:
        raise ValueError("format evidence path must identify one directory inside docs/evidence")
    return evidence


def format_evidence_checks(spec: dict[str, Any]) -> tuple[
    list[dict[str, Any]], dict[str, str], dict[str, str]
]:
    checks: list[dict[str, Any]] = []
    inputs: dict[str, str] = {}
    artifacts: dict[str, str] = {}
    try:
        evidence = registered_format_evidence(spec)
        probe_path = evidence / "validation/probe-result.json"
        dwg_path = evidence / "dwg/capability.json"
        gate_path = evidence / "gate-result.json"
        probe = load_json(probe_path)
        dwg = load_json(dwg_path)
        gate = load_json(gate_path)
        if probe.get("status") != "passed" or len(probe.get("pages", [])) != 3:
            raise ValueError("DXF/PDF probe is not a three-page technical pass")
        for mapping_name, destination in (("validated_candidate_hashes", artifacts),):
            mapping = probe.get(mapping_name)
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError(f"probe {mapping_name} is empty")
            for relative, expected in mapping.items():
                path = Path(relative)
                if not path.is_absolute():
                    path = resolve_project_path(relative)
                if not path.is_file() or file_sha256(path) != expected:
                    raise ValueError(f"probe hash mismatch: {relative}")
                key = (
                    str(path.relative_to(ROOT)).replace("\\", "/")
                    if path.is_relative_to(ROOT)
                    else str(path)
                )
                destination[key] = expected
        checks.append(
            {
                "id": "dxf-pdf-technical-evidence",
                "status": "passed",
                "detail": "three editable R2018 DXF pages, A4 PDF/PNG, glyph and native dimension readback passed",
            }
        )
        decision = load_json(ROOT / "docs/decisions/format-profile.json")
        choice = decision.get("dwg_release_decision")
        if choice == "postpone_keep_dxf_pdf_baseline":
            if dwg.get("conversion_run") is not False or dwg.get("status") != "blocked":
                raise ValueError("postponed DWG evidence must truthfully record an unrun blocked probe")
            dwg_detail = "postponed converter remains unrun and blocked"
        elif choice == "first_release_required":
            if dwg.get("conversion_run") is not False or dwg.get("status") != "available_verified_evaluation_only" or gate.get("status") != "passed":
                raise ValueError("required DWG lacks verified capability and a passed format gate")
            dwg_detail = "required DWG capability and format gate are verified"
        elif choice == "pending_user_decision":
            if dwg.get("conversion_run") is not False or dwg.get("status") != "blocked":
                raise ValueError("pending DWG decision must retain the truthful unrun blocked probe")
            dwg_detail = "DWG decision remains pending; converter is truthfully unrun and blocked"
        else:
            raise ValueError("DWG release decision is invalid")
        checks.append(
            {
                "id": "dwg-probe-policy",
                "status": "passed",
                "detail": dwg_detail,
            }
        )
        if gate.get("status") not in {"blocked", "passed"}:
            raise ValueError("format gate result is invalid")
        checks.append(
            {
                "id": "format-gate-record",
                "status": "passed",
                "detail": f"machine gate is {gate['status']}; human approval is evaluated separately",
            }
        )
        for path in (
            probe_path,
            dwg_path,
            gate_path,
            evidence / "human-approval.json",
            ROOT / "docs/decisions/format-profile.json",
            ROOT / "fixtures/synthetic/heater_sample.json",
            ROOT / "templates/heater-a4-v1/layout.json",
            ROOT / "templates/heater-a4-v1/fonts.json",
            ROOT / "templates/heater-a4-v1/manifest.json",
            ROOT / "templates/heater-a4-v1/template.dxf",
        ):
            inputs[str(path.relative_to(ROOT)).replace("\\", "/")] = file_sha256(path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        checks.append(
            {
                "id": "format-evidence",
                "status": "failed",
                "detail": str(exc),
            }
        )
    return checks, inputs, artifacts


def run_commands(
    summary: dict[str, Any],
    commands: list[dict[str, Any]],
    report_dir: Path,
) -> tuple[bool, bool]:
    failed = False
    blocked = False
    for command in commands:
        required = command.get("required", True)
        try:
            argv = [part.format(python=sys.executable) for part in command["argv"]]
        except (KeyError, ValueError) as exc:
            add_check(summary, f"command-{command.get('id')}", "failed", str(exc))
            failed = True
            continue
        log_path = report_dir / f"{command['id']}.log"
        try:
            result = subprocess.run(
                argv,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                shell=False,
            )
            output = result.stdout + result.stderr
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(output, encoding="utf-8")
            status, detail = classify_command_result(
                command, result.returncode, output
            )
            if required and status == "failed":
                failed = True
            if required and status == "blocked":
                blocked = True
            if required and status != "passed":
                summary["blockers"].append(f"{command['id']}: {detail}")
            summary["commands"].append(
                {
                    "id": command["id"],
                    "argv": argv,
                    "cwd": str(ROOT),
                    "exit_code": result.returncode,
                    "required": required,
                    "status": status,
                    "detail": detail,
                    "log": str(log_path.relative_to(ROOT)),
                    "log_sha256": file_sha256(log_path),
                }
            )
        except FileNotFoundError as exc:
            blocked = blocked or required
            detail = f"executable not found: {exc}"
            if required:
                summary["blockers"].append(f"{command['id']}: {detail}")
            summary["commands"].append(
                {
                    "id": command["id"],
                    "argv": argv,
                    "cwd": str(ROOT),
                    "exit_code": None,
                    "required": required,
                    "status": "blocked",
                    "detail": detail,
                }
            )
    return failed, blocked


def run_builtin_checks(
    summary: dict[str, Any],
    names: Any,
    spec: dict[str, Any],
) -> tuple[bool, bool]:
    if names is None:
        names = []
    if not isinstance(names, list):
        add_check(summary, "builtin-checks", "failed", "builtin_checks must be a list")
        return True, False
    failed = False
    for name in names:
        if name == "fixtures":
            checks, inputs = fixture_checks()
            summary["input_hashes"].update(inputs)
        elif name == "foundation":
            checks, artifacts = foundation_checks()
            summary["artifact_hashes"].update(artifacts)
        elif name == "format-evidence":
            checks, inputs, artifacts = format_evidence_checks(spec)
            summary["input_hashes"].update(inputs)
            summary["artifact_hashes"].update(artifacts)
        else:
            add_check(
                summary,
                "builtin-checks",
                "failed",
                f"unknown builtin check: {name}",
            )
            failed = True
            continue
        summary["checks"].extend(checks)
        failed = failed or any(item["status"] != "passed" for item in checks)
        for item in checks:
            if item["status"] != "passed":
                summary["blockers"].append(f"{item['id']}: {item['detail']}")
    return failed, False


def finish(
    report_dir: Path,
    summary: dict[str, Any],
    *,
    failed: bool,
    blocked: bool,
) -> int:
    if failed:
        summary["status"] = "failed"
        exit_code = 1
    elif blocked:
        summary["status"] = "blocked"
        exit_code = 2
    else:
        summary["status"] = "passed"
        exit_code = 0
    write_summary(report_dir, summary)
    return exit_code


def run_batch(
    batch: str,
    report_dir: Path,
    registry_path: Path = REGISTRY,
) -> int:
    summary = initial_summary(batch)
    if not BATCH_PATTERN.fullmatch(batch):
        add_check(summary, "batch-id", "failed", "invalid batch identifier")
        return finish(report_dir, summary, failed=True, blocked=False)
    try:
        registry = load_json(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        add_check(summary, "registry", "failed", str(exc))
        return finish(report_dir, summary, failed=True, blocked=False)
    spec = registry.get("batches", {}).get(batch)
    if spec is None:
        add_check(
            summary,
            "registry",
            "blocked",
            "batch is not implemented in acceptance registry",
        )
        return finish(report_dir, summary, failed=False, blocked=True)

    failed, blocked = validate_registry(summary, spec)
    dep_failed, dep_blocked = validate_dependency_reports(
        summary,
        spec.get("dependency_reports"),
        registry,
    )
    human_failed, human_blocked = validate_human_gates(
        summary,
        spec.get("human_gates"),
    )
    boundary_failed, boundary_blocked = validate_boundary_evidence(
        summary,
        spec.get("boundary_evidence"),
    )
    failed = failed or dep_failed or human_failed or boundary_failed
    blocked = blocked or dep_blocked or human_blocked or boundary_blocked

    if not failed:
        command_failed, command_blocked = run_commands(
            summary,
            spec["commands"],
            report_dir,
        )
        builtin_failed, builtin_blocked = run_builtin_checks(
            summary,
            spec.get("builtin_checks"),
            spec,
        )
        failed = failed or command_failed or builtin_failed
        blocked = blocked or command_blocked or builtin_blocked
    return finish(report_dir, summary, failed=failed, blocked=blocked)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch")
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    report_dir = args.report_dir.resolve()
    evidence_root = (ROOT / "docs/evidence").resolve()
    if not report_dir.is_relative_to(evidence_root):
        parser.error("report-dir must be inside docs/evidence")
    return run_batch(args.batch, report_dir)


if __name__ == "__main__":
    raise SystemExit(main())
