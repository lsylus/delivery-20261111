from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "check_source_boundary",
    ROOT / "scripts/check_source_boundary.py",
)
assert SPEC and SPEC.loader
boundary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boundary)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def fake_reference_root(tmp_path: Path) -> Path:
    root = tmp_path / "references"
    root.mkdir()
    for name in boundary.REPOSITORIES:
        repo = root / name
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "boundary-test")
        git(repo, "config", "user.email", "boundary@test")
        (repo / "tracked.txt").write_text("baseline", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "baseline")
    for relative in boundary.REFERENCE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("reference", encoding="utf-8")
    return root


def test_boundary_detects_same_path_content_changes_without_writing(
    tmp_path: Path,
) -> None:
    root = fake_reference_root(tmp_path)
    repo = root / boundary.REPOSITORIES[0]
    tracked = repo / "tracked.txt"
    baseline = boundary.collect(reference_root=root, project_root=ROOT)
    before_bytes = tracked.read_bytes()
    assert baseline["status"] == "passed"
    assert tracked.read_bytes() == before_bytes

    tracked.write_text("external A", encoding="utf-8")
    first = boundary.collect(
        baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert first["comparison"]["status"] == "changes_observed"
    first_snapshot = boundary.collect(reference_root=root, project_root=ROOT)

    tracked.write_text("external B", encoding="utf-8")
    second = boundary.collect(
        first_snapshot,
        reference_root=root,
        project_root=ROOT,
    )
    assert second["comparison"]["status"] == "changes_observed"
    assert (
        first_snapshot["repositories"][0]["state_sha256"]
        != second["repositories"][0]["state_sha256"]
    )
    assert all(
        change["attribution"] == "unknown_external"
        for change in second["comparison"]["changes"]
    )
    assert tracked.read_text(encoding="utf-8") == "external B"


def test_boundary_detects_commit_reference_and_untracked_changes(
    tmp_path: Path,
) -> None:
    root = fake_reference_root(tmp_path)
    baseline = boundary.collect(reference_root=root, project_root=ROOT)
    repo = root / boundary.REPOSITORIES[1]
    (repo / "new.txt").write_text("untracked", encoding="utf-8")
    changed = boundary.collect(
        baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert changed["comparison"]["status"] == "changes_observed"

    git(repo, "add", "new.txt")
    git(repo, "commit", "-qm", "advance")
    committed = boundary.collect(
        baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert any(
        item["kind"] == "repository_head_changed"
        for item in committed["comparison"]["changes"]
    )

    reference = root / boundary.REFERENCE_FILES[0]
    reference.write_text("reference changed", encoding="utf-8")
    reference_changed = boundary.collect(
        baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert any(
        item["kind"] == "reference_file_changed"
        for item in reference_changed["comparison"]["changes"]
    )


def test_boundary_missing_or_invalid_baseline_fails(tmp_path: Path) -> None:
    root = fake_reference_root(tmp_path)
    missing_repo = root / boundary.REPOSITORIES[-1]
    missing_repo.rename(root / "missing")
    result = boundary.collect(reference_root=root, project_root=ROOT)
    assert result["status"] == "failed"
    assert result["missing"]

    invalid_baseline = {"schema_version": 1, "status": "passed"}
    compared = boundary.collect(
        invalid_baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert compared["status"] == "failed"
    assert compared["errors"]

    empty_baseline = {
        "schema_version": 2,
        "status": "passed",
        "mode": "snapshot",
        "checked_at": "2026-11-07T00:00:00+00:00",
        "reference_root": str(root),
        "project_source_sha256": boundary.source_contract_sha256(ROOT),
        "repositories": [],
        "reference_files": [],
        "missing": [],
        "errors": [],
        "attribution": "observation_only",
    }
    compared = boundary.collect(
        empty_baseline,
        reference_root=root,
        project_root=ROOT,
    )
    assert compared["status"] == "failed"
    assert compared["comparison"]["status"] == "invalid_baseline"


def test_snapshot_validation_rejects_truncation_and_inconsistent_hashes(
    tmp_path: Path,
) -> None:
    root = fake_reference_root(tmp_path)
    snapshot = boundary.collect(reference_root=root, project_root=ROOT)
    boundary.validate_snapshot(snapshot)

    missing_repository = deepcopy(snapshot)
    missing_repository["repositories"].pop()
    with pytest.raises(ValueError, match="repository coverage"):
        boundary.validate_snapshot(missing_repository)

    missing_reference = deepcopy(snapshot)
    missing_reference["reference_files"].pop()
    with pytest.raises(ValueError, match="reference file coverage"):
        boundary.validate_snapshot(missing_reference)

    bad_state = deepcopy(snapshot)
    bad_state["repositories"][0]["state_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="state_sha256"):
        boundary.validate_snapshot(bad_state)

    bad_untracked = deepcopy(snapshot)
    bad_untracked["repositories"][0]["untracked_files"] = [
        {"path": "new.txt", "kind": "file", "bytes": 1, "sha256": "bad"}
    ]
    with pytest.raises(ValueError, match="untracked sha256"):
        boundary.validate_snapshot(bad_untracked)
