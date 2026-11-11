#!/usr/bin/env python3
"""Capture and compare read-only state of external reference repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evidence_common import file_sha256, source_contract_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = Path("/data/qmh/satellite-plugins-20261029")
REPOSITORIES = (
    "dsh-satellite-geometry",
    "dsh-satellite-thermal",
    "microservice-refactor",
    "microservice-refactor-shared-core",
    "dsh-satellite-drawings",
)
REFERENCE_FILES = (
    "microservice-refactor-shared-core/dsh-satellite-geometry/plugin/package.json",
    "microservice-refactor-shared-core/dsh-satellite-geometry/plugin/src/host-runtime.mjs",
    "microservice-refactor-shared-core/dsh-satellite-geometry/plugin/src/workspace.mjs",
    "dsh-satellite-drawings/service/src/thermal_drawings/drawing/converter.py",
    "dsh-satellite-drawings/docs/evidence/B04/capability.json",
    "dsh-satellite-drawings/docs/evidence/B04/acceptance.json",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def run_git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_state_sha256(
    head: str,
    porcelain: list[str],
    tracked_diff_sha256: str,
    untracked: list[dict[str, object]],
) -> str:
    state_material = json.dumps(
        {
            "head": head,
            "porcelain": porcelain,
            "tracked_diff_sha256": tracked_diff_sha256,
            "untracked": untracked,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(state_material)


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _require_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return timestamp.astimezone(timezone.utc)


def validate_snapshot(
    payload: dict[str, Any],
    *,
    allow_comparison: bool = False,
) -> None:
    """Validate a complete read-only boundary snapshot before it is trusted."""

    if not isinstance(payload, dict):
        raise ValueError("boundary snapshot must be an object")
    if payload.get("schema_version") != 2:
        raise ValueError("boundary snapshot schema_version must be 2")
    if payload.get("status") != "passed":
        raise ValueError("boundary snapshot status must be passed")
    allowed_modes = {"snapshot", "comparison"} if allow_comparison else {"snapshot"}
    if payload.get("mode") not in allowed_modes:
        raise ValueError("boundary snapshot mode is invalid")
    if payload.get("mode") == "snapshot" and (
        "baseline_sha256" in payload or "comparison" in payload
    ):
        raise ValueError("baseline snapshot must not contain comparison fields")
    if not isinstance(payload.get("reference_root"), str):
        raise ValueError("boundary snapshot reference_root is missing")
    _require_timestamp(payload.get("checked_at"), "checked_at")
    _require_sha256(payload.get("project_source_sha256"), "project_source_sha256")
    if payload.get("missing") != [] or payload.get("errors") != []:
        raise ValueError("boundary snapshot has missing paths or errors")
    if payload.get("attribution") != "observation_only":
        raise ValueError("boundary snapshot attribution must be observation_only")

    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("boundary snapshot repositories must be a list")
    names = [item.get("name") for item in repositories if isinstance(item, dict)]
    if len(names) != len(repositories) or set(names) != set(REPOSITORIES):
        raise ValueError("boundary snapshot repository coverage is incomplete")
    if len(names) != len(set(names)):
        raise ValueError("boundary snapshot repositories contain duplicates")
    for item in repositories:
        name = str(item["name"])
        if not isinstance(item.get("path"), str):
            raise ValueError(f"repository {name} path is missing")
        head = item.get("head")
        if not isinstance(head, str) or GIT_HEAD_PATTERN.fullmatch(head) is None:
            raise ValueError(f"repository {name} head is invalid")
        dirty_files = item.get("dirty_files")
        if not isinstance(dirty_files, list) or not all(
            isinstance(value, str) for value in dirty_files
        ):
            raise ValueError(f"repository {name} dirty_files is invalid")
        if item.get("dirty_count") != len(dirty_files):
            raise ValueError(f"repository {name} dirty_count is inconsistent")
        tracked_bytes = item.get("tracked_diff_bytes")
        if type(tracked_bytes) is not int or tracked_bytes < 0:
            raise ValueError(f"repository {name} tracked_diff_bytes is invalid")
        tracked_hash = _require_sha256(
            item.get("tracked_diff_sha256"),
            f"repository {name} tracked_diff_sha256",
        )
        untracked = item.get("untracked_files")
        if not isinstance(untracked, list):
            raise ValueError(f"repository {name} untracked_files is invalid")
        untracked_paths: list[str] = []
        for entry in untracked:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError(f"repository {name} has invalid untracked entry")
            untracked_paths.append(entry["path"])
            kind = entry.get("kind")
            if kind not in {"file", "symlink", "missing_or_special"}:
                raise ValueError(f"repository {name} has invalid untracked kind")
            if kind == "missing_or_special":
                if entry.get("bytes") is not None or entry.get("sha256") is not None:
                    raise ValueError(f"repository {name} special entry is inconsistent")
            else:
                size = entry.get("bytes")
                if type(size) is not int or size < 0:
                    raise ValueError(f"repository {name} untracked size is invalid")
                _require_sha256(
                    entry.get("sha256"), f"repository {name} untracked sha256"
                )
        if len(untracked_paths) != len(set(untracked_paths)):
            raise ValueError(f"repository {name} has duplicate untracked paths")
        expected_state = repository_state_sha256(
            head,
            dirty_files,
            tracked_hash,
            untracked,
        )
        if item.get("state_sha256") != expected_state:
            raise ValueError(f"repository {name} state_sha256 is inconsistent")

    references = payload.get("reference_files")
    if not isinstance(references, list):
        raise ValueError("boundary snapshot reference_files must be a list")
    relative_paths = [
        item.get("relative_path") for item in references if isinstance(item, dict)
    ]
    if len(relative_paths) != len(references) or set(relative_paths) != set(
        REFERENCE_FILES
    ):
        raise ValueError("boundary snapshot reference file coverage is incomplete")
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("boundary snapshot reference files contain duplicates")
    for item in references:
        relative = str(item["relative_path"])
        if not isinstance(item.get("path"), str):
            raise ValueError(f"reference file {relative} path is missing")
        size = item.get("bytes")
        if type(size) is not int or size < 0:
            raise ValueError(f"reference file {relative} size is invalid")
        _require_sha256(item.get("sha256"), f"reference file {relative} sha256")


def untracked_entries(repo: Path) -> list[dict[str, object]]:
    output = run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        text=False,
    )
    assert isinstance(output, bytes)
    entries: list[dict[str, object]] = []
    for raw_name in output.split(b"\0"):
        if not raw_name:
            continue
        name = os.fsdecode(raw_name)
        path = repo / name
        if path.is_symlink():
            data = os.readlink(path).encode("utf-8", errors="surrogateescape")
            entries.append(
                {
                    "path": name,
                    "kind": "symlink",
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                }
            )
        elif path.is_file():
            entries.append(
                {
                    "path": name,
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
        else:
            entries.append(
                {
                    "path": name,
                    "kind": "missing_or_special",
                    "bytes": None,
                    "sha256": None,
                }
            )
    return sorted(entries, key=lambda item: str(item["path"]))


def repository_snapshot(name: str, repo: Path) -> dict[str, object]:
    porcelain = str(
        run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    ).splitlines()
    tracked_diff = run_git(repo, "diff", "--binary", "HEAD", "--", text=False)
    assert isinstance(tracked_diff, bytes)
    untracked = untracked_entries(repo)
    head = str(run_git(repo, "rev-parse", "HEAD")).strip()
    tracked_diff_sha256 = sha256_bytes(tracked_diff)
    return {
        "name": name,
        "path": str(repo),
        "head": head,
        "dirty_count": len(porcelain),
        "dirty_files": porcelain,
        "tracked_diff_bytes": len(tracked_diff),
        "tracked_diff_sha256": tracked_diff_sha256,
        "untracked_files": untracked,
        "state_sha256": repository_state_sha256(
            head,
            porcelain,
            tracked_diff_sha256,
            untracked,
        ),
    }


def snapshot(
    *,
    reference_root: Path = REFERENCE_ROOT,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    repositories: list[dict[str, object]] = []
    references: list[dict[str, object]] = []
    missing: list[str] = []
    errors: list[dict[str, str]] = []

    for name in REPOSITORIES:
        repo = reference_root / name
        if not (repo / ".git").exists():
            missing.append(str(repo))
            continue
        try:
            repositories.append(repository_snapshot(name, repo))
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append({"path": str(repo), "error": str(exc)})

    for relative in REFERENCE_FILES:
        path = reference_root / relative
        if not path.is_file():
            missing.append(str(path))
            continue
        try:
            references.append(
                {
                    "relative_path": relative,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})

    return {
        "schema_version": 2,
        "status": "passed" if not missing and not errors else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "snapshot",
        "reference_root": str(reference_root),
        "project_source_sha256": source_contract_sha256(project_root),
        "repositories": repositories,
        "reference_files": references,
        "missing": missing,
        "errors": errors,
        "attribution": "observation_only",
    }


def snapshot_hash(value: dict[str, Any]) -> str:
    stable = {
        key: item
        for key, item in value.items()
        if key not in {"comparison", "baseline_sha256"}
    }
    return sha256_bytes(
        json.dumps(
            stable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def compare_snapshots(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    before_repositories = {
        item["name"]: item for item in baseline.get("repositories", [])
    }
    after_repositories = {
        item["name"]: item for item in current.get("repositories", [])
    }
    for name in sorted(set(before_repositories) | set(after_repositories)):
        before = before_repositories.get(name)
        after = after_repositories.get(name)
        if before is None or after is None:
            changes.append(
                {
                    "kind": "repository_availability_changed",
                    "name": name,
                    "before": before,
                    "after": after,
                    "attribution": "unknown_external",
                }
            )
            continue
        if before["head"] != after["head"]:
            changes.append(
                {
                    "kind": "repository_head_changed",
                    "name": name,
                    "before": before["head"],
                    "after": after["head"],
                    "attribution": "unknown_external",
                }
            )
        if before["state_sha256"] != after["state_sha256"]:
            changes.append(
                {
                    "kind": "repository_worktree_changed",
                    "name": name,
                    "before": before["state_sha256"],
                    "after": after["state_sha256"],
                    "attribution": "unknown_external",
                }
            )

    before_files = {
        item["relative_path"]: item for item in baseline.get("reference_files", [])
    }
    after_files = {
        item["relative_path"]: item for item in current.get("reference_files", [])
    }
    for name in sorted(set(before_files) | set(after_files)):
        before = before_files.get(name)
        after = after_files.get(name)
        before_hash = before.get("sha256") if before else None
        after_hash = after.get("sha256") if after else None
        if before_hash != after_hash:
            changes.append(
                {
                    "kind": "reference_file_changed",
                    "name": name,
                    "before": before_hash,
                    "after": after_hash,
                    "attribution": "unknown_external",
                }
            )

    return {
        "status": "unchanged" if not changes else "changes_observed",
        "changes": changes,
        "interpretation": (
            "No external reference change observed."
            if not changes
            else "External reference state changed; attribution is unknown and no files were reverted."
        ),
    }


def collect(
    baseline: dict[str, Any] | None = None,
    *,
    reference_root: Path = REFERENCE_ROOT,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    current = snapshot(reference_root=reference_root, project_root=project_root)
    if baseline is None:
        return current
    current["mode"] = "comparison"
    current["baseline_sha256"] = snapshot_hash(baseline)
    try:
        validate_snapshot(baseline)
        if baseline["project_source_sha256"] != current["project_source_sha256"]:
            raise ValueError("baseline source fingerprint does not match current source")
    except (KeyError, TypeError, ValueError) as exc:
        current["status"] = "failed"
        current["errors"].append(
            {"path": "baseline", "error": str(exc)}
        )
        current["comparison"] = {
            "status": "invalid_baseline",
            "changes": [],
            "interpretation": "Baseline is incomplete or does not match current source.",
        }
        return current
    current["comparison"] = compare_snapshots(baseline, current)
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--reference-root", type=Path, default=REFERENCE_ROOT)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8"))
        if args.baseline
        else None
    )
    payload = collect(
        baseline,
        reference_root=args.reference_root,
        project_root=args.project_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
