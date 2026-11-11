import copy
from pathlib import Path
import sys
import pytest
from thermal_drawings.importers.manifest import (
    inventory, candidate_bundle, copy_candidate, verify_manifest, controlled, assembly_digest)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from contracts import validate


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source/'top.asm.5').write_bytes(b'#UGC:2 ASSEMBLY 2063\n#Creo TM 9.0 9.0.8.0\nchild.prt\nmissing.prt\n')
    (source/'child.prt.1').write_bytes(b'#UGC:2 PART 2063\n#Creo TM 9.0 9.0.8.0\n')
    (source/'child.prt.2').write_bytes(b'#UGC:2 PART 2063\n#Creo TM 9.0 9.0.8.0\nchanged geometry\n')
    return candidate_bundle(inventory(source), 'top.asm.5', 'test')


def test_hint_closure_keeps_versions_and_never_claims_complete(bundle):
    m = bundle['source_manifest']
    validate('model', m, 'SourceManifest')
    assert len(m['files']) == 3
    assert m['units'] is None and m['missing_refs'] is None and m['load_status'] == 'not_opened'
    assert bundle['dependency_report']['complete'] is False
    assert any(h['hint'] == 'missing.prt' and not h['candidates'] for h in bundle['dependency_report']['hints'])


def test_isolated_copy_and_changed_dependency_fail(bundle, tmp_path):
    destination = copy_candidate(bundle, tmp_path/'isolated')
    m = bundle['source_manifest']
    assert (destination/'child.prt.1').read_bytes() == (Path(bundle['source_root'])/'child.prt.1').read_bytes()
    (destination/'child.prt.1').write_bytes(b'mutated')
    with pytest.raises(ValueError):
        verify_manifest(destination, m)
    verify_manifest(bundle['source_root'], m)


def test_missing_dependency_is_not_a_complete_success(bundle, tmp_path):
    destination = copy_candidate(bundle, tmp_path/'isolated')
    (destination/'child.prt.2').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_manifest(destination, bundle['source_manifest'])


@pytest.mark.parametrize('bad', ['../secret', '/etc/passwd', 'a/../../b', 'a\\b', 'D:/x', './x', 'a//b', ''])
def test_traversal_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        controlled(tmp_path, bad)


def test_symlinks_and_case_collision_rejected(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    (source/'x.prt').write_text('a')
    (source/'other.prt').symlink_to(source/'x.prt')
    with pytest.raises(ValueError):
        inventory(source)
    (source/'other.prt').unlink()
    (source/'X.prt').write_text('b')
    with pytest.raises(ValueError):
        inventory(source)


def test_digest_is_all_files_order_independent(bundle):
    files = bundle['source_manifest']['files']
    assert assembly_digest(files) == assembly_digest(list(reversed(files)))
    changed = copy.deepcopy(files)
    changed[0]['sha256'] = '0'*64
    assert assembly_digest(files) != assembly_digest(changed)
    with pytest.raises(ValueError):
        assembly_digest(files + [files[0]])


def test_cannot_copy_into_source_or_overwrite(bundle, tmp_path):
    for target in [Path(bundle['source_root'])/'bad', tmp_path]:
        with pytest.raises(ValueError):
            copy_candidate(bundle, target)


def test_source_change_after_inventory_refused(bundle):
    source = Path(bundle['source_root'])
    index = inventory(source)
    (source/'child.prt.1').write_bytes(b'changed')
    with pytest.raises(ValueError):
        candidate_bundle(index, 'top.asm.5', 'test')


def test_forged_format_and_digest_rejected(bundle):
    m = copy.deepcopy(bundle['source_manifest'])
    m['vendor_version'] = '99.0.0.0'
    with pytest.raises(ValueError):
        verify_manifest(bundle['source_root'], m)
    m = copy.deepcopy(bundle['source_manifest'])
    m['assembly_digest'] = '0'*64
    with pytest.raises(ValueError):
        verify_manifest(bundle['source_root'], m)
