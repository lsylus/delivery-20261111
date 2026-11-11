"""Opaque server-owned paths and bounded raw STEP uploads. Archives are rejected."""
import hashlib
import os
from pathlib import Path
import unicodedata
from urllib.parse import unquote
from ..domain.errors import require


def filename(value):
    require(isinstance(value, str), message='A simple STEP basename is required; archives and paths are unsupported')
    value = unicodedata.normalize('NFC', value)
    stem, dot, extension = value.rpartition('.')
    require(dot and extension.lower() in ('step', 'stp') and stem and len(value) <= 125,
            message='A simple STEP basename is required; archives and paths are unsupported')
    require(stem[0].isalnum() and all(character.isalnum() or character in '_.-' for character in stem),
            message='A simple STEP basename is required; archives and paths are unsupported')
    require('..' not in value)
    return value


def header_filename(value):
    require(isinstance(value, str), message='A UTF-8 encoded STEP filename is required')
    try:
        return filename(unquote(value, encoding='utf-8', errors='strict'))
    except UnicodeError:
        require(False, message='A UTF-8 encoded STEP filename is required')


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
