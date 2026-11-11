"""Opaque server-owned paths and bounded raw STEP uploads. Archives are rejected."""
import hashlib
import os
from pathlib import Path
import re
from ..domain.errors import require


def filename(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.(?:step|stp)', value, re.I)),
            message='A simple STEP basename is required; archives and paths are unsupported')
    require('..' not in value)
    return value


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def controlled(root, relative):
    require(isinstance(relative, str) and relative and not relative.startswith('/') and '\\' not in relative and ':' not in relative)
    require(all(p not in ('', '.', '..') for p in relative.split('/')))
    target = root / relative
    require(not any(p.is_symlink() for p in [target, *target.parents]), message='Symlink paths are forbidden')
    require(target.resolve().is_relative_to(root.resolve()), message='Path escapes data root')
    return target


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def check_step(path):
    require(path.stat().st_size > 32, message='Empty or truncated STEP')
    with path.open('rb') as f:
        head = f.read(4096).lstrip()
        f.seek(max(0, path.stat().st_size - 4096))
        tail = f.read()
    require(head.startswith(b'ISO-10303-21;') and tail.rstrip().endswith(b'END-ISO-10303-21;'), message='Only complete single-file STEP input is supported')
