from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "verify_batch",
    ROOT / "scripts/verify_batch.py",
)
assert SPEC and SPEC.loader
verify_batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_batch)
import check_source_boundary as boundary


def write_registry(root: Path, spec: dict[str, object]) -> Path:
    consumer = deepcopy(spec)
    producer_commands = consumer.pop(
        "_producer_commands",
        [
            {
                "id": "tests",
                "argv": [sys.executable, "-c", "print('producer fixture')"],
                "required": True,
            }
        ],
    )
    registry = root / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "batches": {
                    "B00": {"commands": producer_commands},
                    "B99": consumer,
                }
            }
        ),
        encoding="utf-8",
    )
    return registry


def run_case(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    spec: dict[str, object],
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(verify_batch, "ROOT", root)
    report = root / "evidence" / f"run-{len(list((root / 'evidence').glob('*'))) if (root / 'evidence').exists() else 0}"
    exit_code = verify_batch.run_batch(
        "B99",
        report,
        write_registry(root, spec),
    )
    summary = json.loads((report / "summary.json").read_text(encoding="utf-8"))
    required = {
        "batch",
        "status",
        "source_git_head",
        "source_contract_sha256",
        "dependency_reports",
        "commands",
        "checks",
        "input_hashes",
        "artifact_hashes",
        "human_decisions",
        "blockers",
        "timestamp",
    }
    assert required <= set(summary)
    return exit_code, summary


def pytest_command(path: Path) -> dict[str, object]:
    return {
        "id": "pytest",
        "argv": [sys.executable, "-m", "pytest", "-q", str(path)],
        "kind": "pytest",
        "required": True,
    }


def basic_spec(command: dict[str, object]) -> dict[str, object]:
    return {
        "dependency_reports": [],
        "human_gates": [],
        "commands": [command],
        "builtin_checks": [],
    }


def test_real_pytest_success_failure_zero_and_skip_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = {
        "pass": "def test_ok(): assert True\n",
        "fail": "def test_bad(): assert False\n",
        "zero": "# no tests\n",
        "all_skip": (
            "import pytest\n"
            "@pytest.mark.skip(reason='missing')\n"
            "def test_skip(): assert False\n"
        ),
        "mixed_skip": (
            "import pytest\n"
            "def test_ok(): assert True\n"
            "@pytest.mark.skip(reason='required missing')\n"
            "def test_required(): assert False\n"
        ),
    }
    expected = {
        "pass": (0, "passed"),
        "fail": (1, "failed"),
        "zero": (1, "failed"),
        "all_skip": (1, "failed"),
        "mixed_skip": (1, "failed"),
    }
    for name, source in cases.items():
        path = tmp_path / f"test_{name}.py"
        path.write_text(source, encoding="utf-8")
        exit_code, summary = run_case(
            monkeypatch,
            tmp_path,
            basic_spec(pytest_command(path)),
        )
        assert (exit_code, summary["status"]) == expected[name]
        assert len(summary["commands"]) == 1


@pytest.mark.parametrize(
    "output",
    [
        "1 failed, 1 passed in 0.01s\n",
        "1 passed, 1 error in 0.01s\n",
        "1 passed in 0.01s\n!!!!!!!! Interrupted: stopped early !!!!!!!!\n",
        "1 passed in 0.01s\n!!!!!!!! KeyboardInterrupt !!!!!!!!\n",
        "1 passed in 0.01s\n!!!!!!!! _pytest.outcomes.Exit: stopped early !!!!!!!!\n",
        "1 passed in 0.01s\nINTERNALERROR> internal pytest failure\n",
    ],
)
def test_pytest_success_exit_cannot_override_failure_error_or_abort(
    output: str,
) -> None:
    status, _ = verify_batch.classify_pytest(0, output, required=True)
    assert status == "failed"


def test_missing_test_is_failed_but_missing_executable_or_package_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, summary = run_case(
        monkeypatch,
        tmp_path,
        basic_spec(pytest_command(tmp_path / "missing_test.py")),
    )
    assert (exit_code, summary["status"]) == (1, "failed")

    missing_executable = {
        "id": "missing-executable",
        "argv": ["/definitely-missing-b01-tool"],
        "required": True,
    }
    exit_code, summary = run_case(
        monkeypatch,
        tmp_path,
        basic_spec(missing_executable),
    )
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert summary["commands"][0]["exit_code"] is None

    missing_package = {
        "id": "missing-package",
        "argv": [sys.executable, "-m", "definitely_missing_b01_package"],
        "required": True,
    }
    exit_code, summary = run_case(
        monkeypatch,
        tmp_path,
        basic_spec(missing_package),
    )
    assert (exit_code, summary["status"]) == (2, "blocked")


def test_optional_blocked_dwg_probe_does_not_block_full_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_approval = tmp_path / "synthetic-human-approval.json"
    synthetic_approval.write_text(json.dumps({
        "status": "approved", "actor": "TEST_FIXTURE_ONLY",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "scope": ["isolated runner policy test"], "artifact_hashes": {"fixture": "test-only"},
    }), encoding="utf-8")
    spec = {
        "dependency_reports": [],
        "human_gates": [{
            "id": "synthetic-cad-approval", "evidence_path": synthetic_approval.name,
            "sha256": verify_batch.file_sha256(synthetic_approval),
        }],
        "builtin_checks": [],
        "commands": [
            {"id": "technical-and-postpone-gate", "argv": [sys.executable, "-c", "print('synthetic gate passed')"], "required": True},
            {"id": "probe-dwg-candidate", "argv": [sys.executable, "-c", "raise SystemExit(2)"], "required": False, "blocked_exit_codes": [2]},
        ],
    }
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (0, "passed")
    dwg = next(item for item in summary["commands"] if item["id"] == "probe-dwg-candidate")
    assert dwg["status"] == "blocked" and dwg["required"] is False


def test_required_dwg_probe_still_blocks_full_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = basic_spec({
        "id": "probe-dwg-candidate", "argv": [sys.executable, "-c", "raise SystemExit(2)"],
        "required": True, "blocked_exit_codes": [2],
    })
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert summary["commands"][0]["exit_code"] == 2


def test_empty_commands_and_unregistered_batch_never_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, summary = run_case(
        monkeypatch,
        tmp_path,
        {"dependency_reports": [], "human_gates": [], "commands": []},
    )
    assert (exit_code, summary["status"]) == (1, "failed")
    assert any(item["id"] == "registry" for item in summary["checks"])

    monkeypatch.setattr(verify_batch, "ROOT", tmp_path)
    output = tmp_path / "unregistered"
    exit_code = verify_batch.run_batch("B99", output, ROOT / "scripts/acceptance_registry.json")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert (exit_code, summary["status"]) == (2, "blocked")


def test_expected_nonzero_command_exit_can_be_required_and_pass() -> None:
    spec = basic_spec(
        {
            "id": "expected-invalid-input",
            "argv": [sys.executable, "-c", "raise SystemExit(1)"],
            "required": True,
            "expected_exit_codes": [1],
        }
    )
    with tempfile.TemporaryDirectory(prefix="runner-expected-exit-") as value:
        root = Path(value)
        with pytest.MonkeyPatch.context() as monkeypatch:
            exit_code, summary = run_case(monkeypatch, root, spec)
    assert (exit_code, summary["status"]) == (0, "passed")
    assert summary["commands"][0]["exit_code"] == 1


@pytest.mark.parametrize("value", [[], [0, 0], [-1], ["1"]])
def test_expected_exit_code_contract_rejects_invalid_lists(
    value: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = {
        "id": "invalid-expected-exit",
        "argv": [sys.executable, "-c", "raise SystemExit(0)"],
        "required": True,
        "expected_exit_codes": value,
    }
    exit_code, summary = run_case(monkeypatch, tmp_path, basic_spec(command))
    assert (exit_code, summary["status"]) == (1, "failed")


def dependency_report(
    root: Path,
    *,
    status: str = "passed",
    timestamp: datetime | None = None,
    source: str = "source-head",
    source_contract: str = "a" * 64,
) -> dict[str, object]:
    evidence = root / "dependency-evidence"
    evidence.mkdir(exist_ok=True)
    log = evidence / "tests.log"
    input_path = evidence / "input.txt"
    artifact = evidence / "artifact.bin"
    log.write_text("1 passed\n", encoding="utf-8")
    input_path.write_text("input\n", encoding="utf-8")
    artifact.write_bytes(b"artifact\n")
    return {
        "batch": "B00",
        "status": status,
        "source_git_head": source,
        "source_contract_sha256": source_contract,
        "contract_version": "1",
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "commands": [
            {
                "id": "tests",
                "status": "passed",
                "exit_code": 0,
                "required": True,
                "log": "dependency-evidence/tests.log",
                "log_sha256": verify_batch.file_sha256(log),
            }
        ],
        "checks": [{"id": "check", "status": "passed"}],
        "input_hashes": {
            "dependency-evidence/input.txt": verify_batch.file_sha256(input_path)
        },
        "artifact_hashes": {
            "dependency-evidence/artifact.bin": verify_batch.file_sha256(artifact)
        },
        "blockers": [],
    }


def dependency_spec(root: Path, report: dict[str, object]) -> dict[str, object]:
    path = root / "dependency.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return {
        "path": "dependency.json",
        "sha256": verify_batch.file_sha256(path),
        "batch": "B00",
        "source_git_head": "source-head",
        "source_contract_sha256": "a" * 64,
        "contract_version": "1",
        "max_age_hours": 24,
    }


def current_dependency_spec(root: Path, report: dict[str, object]) -> dict[str, object]:
    path = root / "current-dependency.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return {
        "path": path.name,
        "verification": "current_source_contract",
        "batch": "B00",
        "source_git_head": "source-head",
        "contract_version": "1",
        "max_age_hours": 24,
    }


def test_current_source_dependency_avoids_embedded_hash_cycle_but_validates_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    current_source = verify_batch.source_contract_sha256(tmp_path)
    report = dependency_report(tmp_path, source_contract=current_source)
    dependency = current_dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0

    report["source_contract_sha256"] = "0" * 64
    (tmp_path / "current-dependency.json").write_text(json.dumps(report), encoding="utf-8")
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert any("content fingerprint" in blocker for blocker in summary["blockers"])


def complete_boundary_pair(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    source_hash = verify_batch.source_contract_sha256(root)
    tracked_hash = verify_batch.file_sha256(Path(__file__).resolve())
    repositories: list[dict[str, object]] = []
    for index, name in enumerate(boundary.REPOSITORIES):
        head = f"{index + 1:x}" * 40
        dirty_files: list[str] = []
        untracked: list[dict[str, object]] = []
        repositories.append(
            {
                "name": name,
                "path": f"/references/{name}",
                "head": head,
                "dirty_count": 0,
                "dirty_files": dirty_files,
                "tracked_diff_bytes": 0,
                "tracked_diff_sha256": tracked_hash,
                "untracked_files": untracked,
                "state_sha256": boundary.repository_state_sha256(
                    head, dirty_files, tracked_hash, untracked
                ),
            }
        )
    references = [
        {
            "relative_path": relative,
            "path": f"/references/{relative}",
            "bytes": index + 1,
            "sha256": f"{index + 1:x}" * 64,
        }
        for index, relative in enumerate(boundary.REFERENCE_FILES)
    ]
    baseline: dict[str, object] = {
        "schema_version": 2,
        "status": "passed",
        "checked_at": checked_at,
        "mode": "snapshot",
        "reference_root": "/references",
        "project_source_sha256": source_hash,
        "repositories": repositories,
        "reference_files": references,
        "missing": [],
        "errors": [],
        "attribution": "observation_only",
    }
    current = deepcopy(baseline)
    current["mode"] = "comparison"
    current["baseline_sha256"] = boundary.snapshot_hash(baseline)
    current["comparison"] = boundary.compare_snapshots(baseline, current)
    return baseline, current


def boundary_spec(
    root: Path,
    baseline: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    baseline_path = root / "boundary-before.json"
    current_path = root / "boundary-after.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")
    return {
        "path": "boundary-after.json",
        "baseline_path": "boundary-before.json",
        "max_age_hours": 24,
    }


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_failed_or_blocked_dependency_is_blocked(
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = dependency_spec(tmp_path, dependency_report(tmp_path, status=status))
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")


def test_missing_stale_version_mismatch_and_changed_dependency_are_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    base = basic_spec(pytest_command(passing))

    missing = {
        "path": "missing.json",
        "sha256": "0" * 64,
        "batch": "B00",
        "source_git_head": "source-head",
        "contract_version": "1",
    }
    spec = {**base, "dependency_reports": [missing]}
    assert run_case(monkeypatch, tmp_path, spec)[0] == 2

    stale = dependency_spec(
        tmp_path,
        dependency_report(
            tmp_path,
            timestamp=datetime.now(timezone.utc) - timedelta(days=2)
        ),
    )
    spec = {**base, "dependency_reports": [stale]}
    assert run_case(monkeypatch, tmp_path, spec)[0] == 2

    mismatch = dependency_spec(
        tmp_path,
        dependency_report(tmp_path, source="other-head"),
    )
    spec = {**base, "dependency_reports": [mismatch]}
    assert run_case(monkeypatch, tmp_path, spec)[0] == 2

    changed = dependency_spec(tmp_path, dependency_report(tmp_path))
    (tmp_path / "dependency.json").write_text(
        json.dumps(dependency_report(tmp_path, status="failed")),
        encoding="utf-8",
    )
    spec = {**base, "dependency_reports": [changed]}
    assert run_case(monkeypatch, tmp_path, spec)[0] == 2


def test_valid_dependency_and_real_subprocess_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    dependency = dependency_spec(tmp_path, dependency_report(tmp_path))
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (0, "passed")
    assert summary["dependency_reports"]["dependency.json"]["sha256"] == dependency["sha256"]


def test_dependency_accepts_runner_resolved_negative_and_optional_blocked_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    report = dependency_report(tmp_path)
    log = report["commands"][0]["log"]
    log_hash = report["commands"][0]["log_sha256"]
    report["commands"] = [
        {
            "id": "required-negative",
            "status": "passed",
            "exit_code": 1,
            "required": True,
            "log": log,
            "log_sha256": log_hash,
        },
        {
            "id": "optional-capability",
            "status": "blocked",
            "exit_code": 2,
            "required": False,
            "log": log,
            "log_sha256": log_hash,
        },
    ]
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    spec["_producer_commands"] = [
        {
            "id": "required-negative",
            "argv": [sys.executable, "-c", "raise SystemExit(1)"],
            "required": True,
            "expected_exit_codes": [1],
        },
        {
            "id": "optional-capability",
            "argv": [sys.executable, "-c", "raise SystemExit(2)"],
            "required": False,
            "blocked_exit_codes": [2],
        },
    ]
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0


@pytest.mark.parametrize("exit_code", [23, -11])
def test_dependency_rejects_normal_command_failure_reported_as_passed(
    exit_code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    report = dependency_report(tmp_path)
    log = tmp_path / str(report["commands"][0]["log"])
    log.write_text("REAL FAILURE\n", encoding="utf-8")
    report["commands"][0]["exit_code"] = exit_code
    report["commands"][0]["log_sha256"] = verify_batch.file_sha256(log)
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    exit_value, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_value, summary["status"]) == (2, "blocked")
    assert any("contradicts" in blocker for blocker in summary["blockers"])


def test_dependency_rejects_failed_pytest_reported_as_passed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    report = dependency_report(tmp_path)
    log = tmp_path / str(report["commands"][0]["log"])
    log.write_text("1 failed in 0.01s\n", encoding="utf-8")
    report["commands"][0]["exit_code"] = 1
    report["commands"][0]["log_sha256"] = verify_batch.file_sha256(log)
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    spec["_producer_commands"] = [
        {
            "id": "tests",
            "argv": [sys.executable, "-m", "pytest"],
            "kind": "pytest",
            "required": True,
        }
    ]
    exit_value, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_value, summary["status"]) == (2, "blocked")
    assert any("contradicts" in blocker for blocker in summary["blockers"])


def test_dependency_rejects_real_mixed_pytest_log_claimed_as_exit_zero_passed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer_test = tmp_path / "test_consumer_pass.py"
    consumer_test.write_text("def test_ok(): assert True\n", encoding="utf-8")
    mixed_test = tmp_path / "test_mixed_result.py"
    mixed_test.write_text(
        "def test_success(): assert True\n"
        "def test_failure(): assert False, 'REAL MIXED FAILURE'\n",
        encoding="utf-8",
    )
    actual = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(mixed_test)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    actual_output = actual.stdout + actual.stderr
    assert actual.returncode == 1
    assert "1 failed, 1 passed" in actual_output

    report = dependency_report(tmp_path)
    log = tmp_path / str(report["commands"][0]["log"])
    log.write_text(actual_output, encoding="utf-8")
    report["commands"][0]["exit_code"] = 0
    report["commands"][0]["status"] = "passed"
    report["commands"][0]["log_sha256"] = verify_batch.file_sha256(log)
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(consumer_test))
    spec["dependency_reports"] = [dependency]
    spec["_producer_commands"] = [
        {
            "id": "tests",
            "argv": [sys.executable, "-m", "pytest"],
            "kind": "pytest",
            "required": True,
        }
    ]
    exit_value, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_value, summary["status"]) == (2, "blocked")
    assert any("contradicts" in blocker for blocker in summary["blockers"])


def test_dependency_rejects_real_pytest_exit_after_pass_claimed_as_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer_test = tmp_path / "test_consumer_pass.py"
    consumer_test.write_text("def test_ok(): assert True\n", encoding="utf-8")
    early_exit_test = tmp_path / "test_early_exit.py"
    early_exit_test.write_text(
        "import pytest\n"
        "def test_success(): assert True\n"
        "def test_stop(): pytest.exit('REAL STOP AFTER ONE PASS')\n",
        encoding="utf-8",
    )
    actual = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(early_exit_test)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    actual_output = actual.stdout + actual.stderr
    assert actual.returncode == 2
    assert "_pytest.outcomes.Exit: REAL STOP AFTER ONE PASS" in actual_output
    assert "1 passed in" in actual_output
    status, _ = verify_batch.classify_pytest(0, actual_output, required=True)
    assert status == "failed"

    report = dependency_report(tmp_path)
    log = tmp_path / str(report["commands"][0]["log"])
    log.write_text(actual_output, encoding="utf-8")
    report["commands"][0]["exit_code"] = 0
    report["commands"][0]["status"] = "passed"
    report["commands"][0]["log_sha256"] = verify_batch.file_sha256(log)
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(consumer_test))
    spec["dependency_reports"] = [dependency]
    spec["_producer_commands"] = [
        {
            "id": "tests",
            "argv": [sys.executable, "-m", "pytest"],
            "kind": "pytest",
            "required": True,
        }
    ]
    exit_value, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_value, summary["status"]) == (2, "blocked")
    assert any("contradicts" in blocker for blocker in summary["blockers"])


def test_dependency_accepts_explicit_empty_optional_evidence_maps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    report = dependency_report(tmp_path)
    report["input_hashes"] = {}
    report["artifact_hashes"] = {}
    dependency = dependency_spec(tmp_path, report)
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0


@pytest.mark.parametrize(
    ("relative", "action"),
    [
        ("dependency-evidence/tests.log", "rewrite"),
        ("dependency-evidence/tests.log", "delete"),
        ("dependency-evidence/input.txt", "rewrite"),
        ("dependency-evidence/input.txt", "delete"),
        ("dependency-evidence/artifact.bin", "rewrite"),
        ("dependency-evidence/artifact.bin", "delete"),
    ],
)
def test_dependency_referenced_evidence_must_exist_and_match_hash(
    relative: str,
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    dependency = dependency_spec(tmp_path, dependency_report(tmp_path))
    if action == "delete":
        (tmp_path / relative).unlink()
    else:
        (tmp_path / relative).write_bytes(b"tampered\n")
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert summary["blockers"]


def test_dependency_source_fingerprint_is_consumed_but_current_doc_head_is_irrelevant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    dependency = dependency_spec(tmp_path, dependency_report(tmp_path))
    spec = basic_spec(pytest_command(passing))
    spec["dependency_reports"] = [dependency]
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0

    dependency["source_contract_sha256"] = "b" * 64
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")
    assert any("content fingerprint" in blocker for blocker in summary["blockers"])


def test_complete_boundary_and_real_external_change_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    baseline, current = complete_boundary_pair(tmp_path)
    spec = basic_spec(pytest_command(passing))
    spec["boundary_evidence"] = boundary_spec(tmp_path, baseline, current)
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0

    current["reference_files"][0]["sha256"] = "f" * 64  # type: ignore[index]
    current["comparison"] = boundary.compare_snapshots(baseline, current)
    assert current["comparison"]["status"] == "changes_observed"  # type: ignore[index]
    spec["boundary_evidence"] = boundary_spec(tmp_path, baseline, current)
    assert run_case(monkeypatch, tmp_path, spec)[0] == 0


@pytest.mark.parametrize(
    "case",
    [
        "empty_arrays",
        "missing_arrays",
        "missing_repository",
        "missing_reference",
        "missing_baseline",
        "bad_baseline_hash",
        "wrong_source",
        "stale",
        "fake_unchanged",
        "changed_baseline",
        "changed_baseline_timestamp",
    ],
)
def test_incomplete_or_forged_boundary_is_blocked(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    baseline, current = complete_boundary_pair(tmp_path)
    if case == "empty_arrays":
        current["repositories"] = []
        current["reference_files"] = []
    elif case == "missing_arrays":
        current.pop("repositories")
        current.pop("reference_files")
    elif case == "missing_repository":
        current["repositories"].pop()  # type: ignore[union-attr]
    elif case == "missing_reference":
        current["reference_files"].pop()  # type: ignore[union-attr]
    elif case == "bad_baseline_hash":
        current["baseline_sha256"] = "0" * 64
    elif case == "wrong_source":
        baseline["project_source_sha256"] = "0" * 64
        current["project_source_sha256"] = "0" * 64
        current["baseline_sha256"] = boundary.snapshot_hash(baseline)
    elif case == "stale":
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        baseline["checked_at"] = old
        current["checked_at"] = old
        current["baseline_sha256"] = boundary.snapshot_hash(baseline)
    elif case == "fake_unchanged":
        current["reference_files"][0]["sha256"] = "f" * 64  # type: ignore[index]
    elif case == "changed_baseline":
        baseline["reference_files"][0]["sha256"] = "e" * 64  # type: ignore[index]
    elif case == "changed_baseline_timestamp":
        baseline["checked_at"] = (
            datetime.fromisoformat(str(baseline["checked_at"])) - timedelta(seconds=1)
        ).isoformat()
    spec = basic_spec(pytest_command(passing))
    spec["boundary_evidence"] = boundary_spec(tmp_path, baseline, current)
    if case == "missing_baseline":
        spec["boundary_evidence"]["baseline_path"] = "missing-baseline.json"  # type: ignore[index]
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")


def test_missing_human_gate_and_invalid_boundary_are_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok(): assert True\n", encoding="utf-8")
    spec = basic_spec(pytest_command(passing))
    spec["human_gates"] = ["engineer-review"]
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")

    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "failed",
                "mode": "comparison",
                "missing": ["reference"],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    spec = basic_spec(pytest_command(passing))
    spec["boundary_evidence"] = {
        "path": "boundary.json",
        "max_age_hours": 24,
    }
    exit_code, summary = run_case(monkeypatch, tmp_path, spec)
    assert (exit_code, summary["status"]) == (2, "blocked")
