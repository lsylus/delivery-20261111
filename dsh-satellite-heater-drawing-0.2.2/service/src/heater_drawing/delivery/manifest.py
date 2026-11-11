"""Hash-bound manifest helpers without recursive self references."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5


ARTIFACT_NAMESPACE = UUID("0cb995fc-33ac-4875-b857-e41751889d94")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_entry(
    root: Path,
    path: Path,
    *,
    run_id: str,
    revision_hash: str,
    kind: str,
    media_type: str,
    row_ids: list[str],
    page_count: int | None = None,
    page_index: int | None = None,
) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    entry: dict[str, Any] = {
        "artifact_id": str(uuid5(ARTIFACT_NAMESPACE, f"{run_id}:{relative}")),
        "run_id": run_id,
        "revision_hash": revision_hash,
        "relative_path": relative,
        "media_type": media_type,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_ids": row_ids,
        "page_count": page_count,
        "page_index": page_index,
        "kind": kind,
    }
    return entry


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
