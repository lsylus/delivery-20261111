"""Shared hashing helpers for B01 acceptance evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

SOURCE_PATHS = (
    ".python-version",
    "README.md",
    "docs/batches/B01.md",
    "docs/contracts.md",
    "docs/reference/requirements.md",
    "docs/reference/source-files.json",
    "fixtures/case/expected.json",
    "fixtures/case/manifest.json",
    "schemas",
    "scripts",
    "service/pyproject.toml",
    "service/src",
    "service/uv.lock",
    "tests",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_contract_entries(root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for value in SOURCE_PATHS:
        path = root / value
        candidates = [path] if path.is_file() else sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and "__pycache__" not in candidate.parts
            and ".pytest_cache" not in candidate.parts
        )
        for candidate in candidates:
            relative = candidate.relative_to(root).as_posix()
            entries.append(
                {
                    "path": relative,
                    "bytes": candidate.stat().st_size,
                    "sha256": file_sha256(candidate),
                }
            )
    return sorted(entries, key=lambda item: str(item["path"]))


def source_contract_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in source_contract_entries(root):
        digest.update(str(entry["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
