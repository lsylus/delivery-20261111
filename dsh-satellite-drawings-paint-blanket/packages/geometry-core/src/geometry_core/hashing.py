"""Independent content addressing; C01 canonical manifest digest."""
import hashlib
import json
from pathlib import Path

def file_sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def digest_files(files) -> str:
    return hashlib.sha256(json.dumps(sorted(files, key=lambda f: f["relative_path"]), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
