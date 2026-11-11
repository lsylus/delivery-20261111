from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_batch_state_matrix",
    PROJECT_ROOT / "scripts/verify_batch.py",
)
assert SPEC and SPEC.loader
verify_batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_batch)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: dict[str, object],
) -> tuple[int, dict[str, object]]:
    registry_path = root / "scripts/acceptance_registry.json"
    _write_json(registry_path, registry)
    monkeypatch.setattr(verify_batch, "ROOT", root)
    monkeypatch.setattr(verify_batch, "REGISTRY", registry_path)
    report_dir = root / "runner-output"
    exit_code = verify_batch.run_batch("B99", report_dir, registry_path)
    return exit_code, json.loads(
        (report_dir / "summary.json").read_text(encoding="utf-8")
    )


def _format_registry() -> dict[str, object]:
    return {
        "batches": {
            "B99": {
                "dependency_reports": [],
                "human_gates": [],
                "builtin_checks": ["format-evidence"],
                "commands": [
                    {
                        "id": "check-format-gate",
                        "argv": [
                            sys.executable,
                            "-c",
                            "print('TEST_FIXTURE_ONLY')",
                            "--evidence",
                            "docs/evidence/B02-fix-3",
                        ],
                        "kind": "command",
                        "required": True,
                    }
                ],
            }
        }
    }


def _format_fixture(
    root: Path,
    *,
    choice: str,
    dwg_status: str,
    conversion_run: bool,
    gate_status: str,
) -> None:
    artifact = root / "candidate.bin"
    artifact.write_bytes(b"TEST_FIXTURE_ONLY\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence = root / "docs/evidence/B02-fix-3"
    _write_json(
        evidence / "validation/probe-result.json",
        {
            "status": "passed",
            "pages": [{"test": 1}, {"test": 2}, {"test": 3}],
            "validated_candidate_hashes": {"candidate.bin": digest},
        },
    )
    _write_json(
        evidence / "dwg/capability.json",
        {
            "status": dwg_status,
            "conversion_run": conversion_run,
            "test_only": True,
        },
    )
    _write_json(
        evidence / "gate-result.json",
        {"status": gate_status, "test_only": True},
    )
    _write_json(
        evidence / "human-approval.json",
        {"status": "TEST_FIXTURE_ONLY", "test_only": True},
    )
    _write_json(
        root / "docs/decisions/format-profile.json",
        {"dwg_release_decision": choice, "test_only": True},
    )
    for relative in (
        "fixtures/synthetic/heater_sample.json",
        "templates/heater-a4-v1/layout.json",
        "templates/heater-a4-v1/fonts.json",
        "templates/heater-a4-v1/manifest.json",
    ):
        _write_json(root / relative, {"test_only": True})
    template = root / "templates/heater-a4-v1/template.dxf"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_bytes(b"TEST_FIXTURE_ONLY\n")


@pytest.mark.parametrize(
    ("case", "choice", "dwg_status", "conversion_run", "gate_status", "expected"),
    [
        (
            "postpone_positive",
            "postpone_keep_dxf_pdf_baseline",
            "blocked",
            False,
            "blocked",
            (0, "passed"),
        ),
        (
            "pending_claimed_conversion_negative",
            "pending_user_decision",
            "available_verified_evaluation_only",
            False,
            "blocked",
            (1, "failed"),
        ),
        (
            "postpone_claimed_conversion_negative",
            "postpone_keep_dxf_pdf_baseline",
            "available_verified_evaluation_only",
            False,
            "blocked",
            (1, "failed"),
        ),
        (
            "required_blocked_negative",
            "first_release_required",
            "blocked",
            False,
            "blocked",
            (1, "failed"),
        ),
        (
            "required_claimed_verified_negative",
            "first_release_required",
            "available_verified_evaluation_only",
            False,
            "blocked",
            (1, "failed"),
        ),
        (
            "required_controlled_positive",
            "first_release_required",
            "available_verified_evaluation_only",
            False,
            "passed",
            (0, "passed"),
        ),
    ],
)
def test_real_runner_dwg_state_matrix_uses_only_test_fixtures(
    case: str,
    choice: str,
    dwg_status: str,
    conversion_run: bool,
    gate_status: str,
    expected: tuple[int, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / case
    root.mkdir()
    _format_fixture(
        root,
        choice=choice,
        dwg_status=dwg_status,
        conversion_run=conversion_run,
        gate_status=gate_status,
    )
    exit_code, summary = _run(root, monkeypatch, _format_registry())
    assert (exit_code, summary["status"]) == expected
    checks = {item["id"]: item for item in summary["checks"]}
    if expected[1] == "passed":
        assert checks["dwg-probe-policy"]["status"] == "passed"
    else:
        assert checks["format-evidence"]["status"] == "failed"


def test_format_evidence_uses_registered_evidence_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "registered-evidence"
    root.mkdir()
    _format_fixture(
        root,
        choice="postpone_keep_dxf_pdf_baseline",
        dwg_status="blocked",
        conversion_run=False,
        gate_status="blocked",
    )
    old_evidence = root / "docs/evidence/B02-fix-3"
    new_evidence = root / "docs/evidence/B02-fix-5"
    old_evidence.rename(new_evidence)
    registry = _format_registry()
    registry["batches"]["B99"]["commands"][0]["argv"][-1] = (
        "docs/evidence/B02-fix-5"
    )

    exit_code, summary = _run(root, monkeypatch, registry)

    assert (exit_code, summary["status"]) == (0, "passed")
    assert "docs/evidence/B02-fix-5/validation/probe-result.json" in summary[
        "input_hashes"
    ]
    assert not any("B02-fix-3" in path for path in summary["input_hashes"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _build_b01_fixture(
    root: Path,
    mutation: str,
) -> dict[str, object]:
    command_contract = [
        {
            "id": "contract-a",
            "argv": [sys.executable, "-c", "print('A')"],
            "kind": "command",
            "required": True,
        },
        {
            "id": "contract-b",
            "argv": [sys.executable, "-c", "print('B')"],
            "kind": "command",
            "required": True,
        },
    ]
    dependency = {
        "batch": "B01",
        "path": "b01-summary.json",
        "verification": "current_source_contract",
        "acceptance_binding_path": "b01-acceptance.json",
        "contract_version": "1",
        "max_age_hours": 24,
        "historical_accepted_report": {
            "path": "historical.json",
            "sha256": "pending",
        },
    }
    registry: dict[str, object] = {
        "batches": {
            "B01": {
                "dependency_reports": [],
                "human_gates": [],
                "boundary_evidence": {
                    "path": "boundary-after.json",
                    "baseline_path": "boundary-before.json",
                    "max_age_hours": 24,
                },
                "builtin_checks": [],
                "commands": command_contract,
            },
            "B99": {
                "dependency_reports": [dependency],
                "human_gates": [],
                "builtin_checks": [],
                "commands": [
                    {
                        "id": "consumer",
                        "argv": [sys.executable, "-c", "print('consumer')"],
                        "kind": "command",
                        "required": True,
                    }
                ],
            },
        }
    }
    registry_path = root / "scripts/acceptance_registry.json"
    _write_json(registry_path, registry)
    (root / "boundary-before.json").write_text("before\n", encoding="utf-8")
    (root / "boundary-after.json").write_text("after\n", encoding="utf-8")
    (root / "artifact.bin").write_bytes(b"artifact\n")
    logs = []
    for name in ("contract-a.log", "contract-b.log"):
        path = root / name
        path.write_text("passed\n", encoding="utf-8")
        logs.append(path)
    historical = root / "historical.json"
    _write_json(historical, {"batch": "B01", "status": "passed"})
    dependency["historical_accepted_report"]["sha256"] = _sha256(historical)  # type: ignore[index]
    _write_json(registry_path, registry)

    source_contract = verify_batch.source_contract_sha256(root)
    report: dict[str, object] = {
        "batch": "B01",
        "status": "passed",
        "source_git_head": "TEST_FIXTURE_ONLY",
        "source_contract_sha256": source_contract,
        "contract_version": "1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commands": [
            {
                "id": contract["id"],
                "argv": contract["argv"],
                "required": True,
                "status": "passed",
                "exit_code": 0,
                "log": logs[index].name,
                "log_sha256": _sha256(logs[index]),
            }
            for index, contract in enumerate(command_contract)
        ],
        "checks": [
            {"id": "registry", "status": "passed"},
            {"id": "source-boundary", "status": "passed"},
        ],
        "input_hashes": {
            name: _sha256(root / name)
            for name in ("boundary-after.json", "boundary-before.json")
        },
        "artifact_hashes": {"artifact.bin": _sha256(root / "artifact.bin")},
        "blockers": [],
    }
    if mutation == "dropped_commands":
        report["commands"] = report["commands"][:-1]  # type: ignore[index]
    elif mutation == "dropped_checks":
        report["checks"] = report["checks"][:-1]  # type: ignore[index]
    elif mutation == "dropped_boundary_inputs":
        report["input_hashes"].pop("boundary-before.json")  # type: ignore[union-attr]
    elif mutation == "replaced_argv":
        report["commands"][0]["argv"] = [sys.executable, "-c", "print('replaced')"]  # type: ignore[index]
    report_path = root / "b01-summary.json"
    _write_json(report_path, report)
    binding = {
        "schema_version": 1,
        "batch": "B01",
        "report_path": "b01-summary.json",
        "report_sha256": _sha256(report_path),
        "source_git_head": report["source_git_head"],
        "source_contract_sha256": source_contract,
        "commands": command_contract,
        "required_checks": ["registry", "source-boundary"],
        "input_paths": ["boundary-after.json", "boundary-before.json"],
        "artifact_paths": ["artifact.bin"],
        "boundary_inputs": ["boundary-after.json", "boundary-before.json"],
        "historical_accepted_report": dependency["historical_accepted_report"],
    }
    _write_json(root / "b01-acceptance.json", binding)
    _git(root, "init")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "user.name", "Test Fixture")
    _git(root, "config", "user.email", "test-fixture@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "test fixture")
    if mutation == "binding_worktree_mutation":
        binding["required_checks"] = ["registry"]
        _write_json(root / "b01-acceptance.json", binding)
    return registry


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("dropped_commands", "command count differs"),
        ("dropped_checks", "required check set/order is incomplete"),
        ("dropped_boundary_inputs", "input/artifact set is incomplete"),
        ("replaced_argv", "command contract drift"),
        ("binding_worktree_mutation", "differs from the current Git HEAD blob"),
    ],
)
def test_real_runner_rejects_incomplete_or_mutated_b01_acceptance(
    mutation: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / mutation
    root.mkdir()
    registry = _build_b01_fixture(root, mutation)
    exit_code, summary = _run(root, monkeypatch, registry)
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert any(message in blocker for blocker in summary["blockers"])

