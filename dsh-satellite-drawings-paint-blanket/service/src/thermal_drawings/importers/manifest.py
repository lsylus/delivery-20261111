"""Read-only native inventory and integrity-checked, isolated candidate bundles."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

from .detect import detect, NATIVE_NAME, reference_hints


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def controlled(root, relative):
    root = Path(root).resolve(strict=True)
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('invalid relative path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or any(p in ('..', '.') for p in relative.split('/')) or '' in relative.split('/'):
        raise ValueError('invalid relative path')
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink not allowed')
    if not path.resolve().is_relative_to(root):
        raise ValueError('path escaped source root')
    return path


def file_record(root, relative):
    path = controlled(root, relative)
    before = path.stat()
    if not path.is_file():
        raise ValueError('not a regular file')
    digest = sha(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('source changed during inventory')
    return dict(relative_path=relative, sha256=digest, bytes=after.st_size)


def assembly_digest(files):
    ordered = sorted(files, key=lambda f: f['relative_path'])
    names = [f['relative_path'].casefold() for f in ordered]
    if not ordered or len(names) != len(set(names)):
        raise ValueError('empty or case-ambiguous file set')
    return hashlib.sha256(json.dumps(ordered, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def inventory(root):
    root = Path(root).resolve(strict=True)
    records, seen = [], set()
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('source inventory contains a symlink')
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.casefold() in seen:
            raise ValueError('case-ambiguous source inventory')
        seen.add(relative.casefold())
        record = file_record(root, relative)
        record['detection'] = detect(path)
        records.append(record)
    return dict(schema_version=1, kind='inventory_not_loaded_assembly',
                source_root=str(root), files=records)


def candidate_bundle(index, main_file, asset_id):
    root = Path(index['source_root'])
    by_path = {f['relative_path']: f for f in index['files']}
    if main_file not in by_path:
        raise ValueError('main file absent from inventory')
    by_model = {}
    for relative in by_path:
        match = NATIVE_NAME.fullmatch(PurePosixPath(relative).name)
        if match:
            key = (match[1] + '.' + match[2]).casefold()
            by_model.setdefault(key, []).append(relative)
    chosen, pending, hint_records = set(), [main_file], []
    while pending:
        relative = pending.pop()
        if relative in chosen:
            continue
        chosen.add(relative)
        entry = by_path[relative]
        expected = {k: entry[k] for k in ('relative_path', 'sha256', 'bytes')}
        if file_record(root, relative) != expected:
            raise ValueError('source differs from inventory')
        for hint in reference_hints(controlled(root, relative)):
            match = NATIVE_NAME.fullmatch(hint)
            key = (match[1] + '.' + match[2]).casefold()
            matches = by_model.get(key, [])
            if match[3]:
                matches = [p for p in matches if PurePosixPath(p).name.casefold() == hint.casefold()]
            # Preserve ALL matching saved versions. No guessed latest revision.
            hint_records.append(dict(source=relative, hint=hint, candidates=sorted(matches),
                                     authoritative=False))
            pending.extend(matches)
    files = [{k: by_path[p][k] for k in ('relative_path', 'sha256', 'bytes')} for p in sorted(chosen)]
    detection = by_path[main_file]['detection']
    manifest = dict(schema_version=1, asset_id=asset_id, main_file=main_file,
                    files=files, assembly_digest=assembly_digest(files),
                    detected_format=detection['detected_format'], vendor=detection['vendor'],
                    vendor_version=detection['vendor_version'], units=None,
                    load_status='not_opened', missing_refs=None, conversion_evidence=None)
    return dict(source_manifest=manifest, source_root=str(root), dependency_report=dict(
        status='unverified', method='plaintext hints plus all matching saved versions',
        complete=False, hints=hint_records, missing_refs=None, suppressed_components=None,
        simplified_representations=None, family_table_resolution=None,
        reason='Only an authorized native loader can establish the actual dependency closure'),
        geometry=dict(status='unverified', solids=None, instances=None, units=None,
                      bounds_mm=None, volume_mm3=None))


def verify_manifest(root, manifest):
    files = manifest['files']
    if assembly_digest(files) != manifest['assembly_digest']:
        raise ValueError('assembly digest mismatch')
    if manifest['main_file'] not in [f['relative_path'] for f in files]:
        raise ValueError('main file absent')
    for entry in files:
        if file_record(root, entry['relative_path']) != entry:
            raise ValueError('manifest file missing or changed: ' + entry['relative_path'])
    observed = detect(controlled(root, manifest['main_file']))
    for key in ('detected_format', 'vendor', 'vendor_version'):
        if manifest[key] != observed[key]:
            raise ValueError('manifest detection mismatch: ' + key)


def copy_candidate(bundle, destination):
    source = Path(bundle['source_root']).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('copy must be isolated from source')
    if destination.exists():
        raise ValueError('destination must be new')
    manifest = bundle['source_manifest']
    verify_manifest(source, manifest)
    destination.mkdir(parents=True)
    try:
        for entry in manifest['files']:
            target = controlled(destination, entry['relative_path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(controlled(source, entry['relative_path']), target)
        verify_manifest(destination, manifest)
        verify_manifest(source, manifest)
    except Exception:
        # Only this newly created directory is owned by this function.
        shutil.rmtree(destination)
        raise
    return destination
