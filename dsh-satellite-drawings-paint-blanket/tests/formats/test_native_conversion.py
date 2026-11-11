from pathlib import Path
import json
import sys
import time
import pytest
from thermal_drawings.importers.manifest import inventory, candidate_bundle
from thermal_drawings.importers.native import NativeConverter, NativeConversionUnavailable, inspect_step_geometry
from thermal_drawings.importers.capabilities import native_capability

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from probe_native import run_bounded, probe, load_native_config


@pytest.mark.parametrize('changes,config,code', [
    ({}, {}, 'converter_not_configured'),
    ({'detected_format':'unknown'}, {}, 'unsupported_format'),
    ({'missing_refs':['part.prt.2']}, {}, 'missing_dependencies'),
    ({}, {'license_state':'denied'}, 'license_unavailable'),
    ({}, {'license_state':'expired'}, 'license_unavailable'),
    ({}, {'supported_versions':['8.0.0.0']}, 'unsupported_version'),
    ({}, {'adapter':'creo_worker','license_state':'authorized'}, 'adapter_not_validated'),
    ({'load_status':'complete','missing_refs':[]}, {}, 'converter_not_configured'),
])
def test_capabilities_fail_closed(changes, config, code):
    m = dict(detected_format='Creo_PART', vendor='PTC Creo', vendor_version='9.0.8.0', missing_refs=None)
    m.update(changes)
    result = native_capability(m, config)
    assert result['code'] == code
    assert result['available'] is False and result['status'] == 'blocked'
    assert result['validated_case_ids'] == []


def test_no_engine_never_produces_step(tmp_path):
    (tmp_path/'part.prt.1').write_bytes(b'#UGC:2 PART 2063\n#Creo TM 9.0 9.0.8.0\n')
    bundle = candidate_bundle(inventory(tmp_path), 'part.prt.1', 'test')
    with pytest.raises(NativeConversionUnavailable):
        NativeConverter().convert(bundle['source_manifest'], tmp_path)
    assert not list(tmp_path.glob('*.step'))


def test_actual_b02_reader_preserves_tree_transform_units():
    result = inspect_step_geometry(ROOT/'fixtures/synthetic/assembly-tree.step')
    assert result['native_equivalence'] == 'not_verified'
    assert result['leaf_instances'] == 3 and len(result['nodes']) == 5
    assert len(result['roots']) == 2
    assert result['step']['volume_mm3'] == pytest.approx(12000.06)
    leaves = [n for n in result['nodes'] if not n['children']]
    first, second = next((a, b) for i, a in enumerate(leaves) for b in leaves[i+1:]
                         if a['definition'] == b['definition'])
    assert first['definition'] == second['definition'] and first['world'] != second['world']
    inch = inspect_step_geometry(ROOT/'fixtures/synthetic/inch-box.step')
    assert inch['step']['volume_mm3'] == pytest.approx(98322.384)
    assert [u.upper() for u in inch['step']['length_units']] == ['INCH']


@pytest.mark.parametrize('content', [b'', b'garbage', b'ISO-10303-21;\nHEADER;\n'])
def test_empty_bad_truncated_step_rejected(tmp_path, content):
    path = tmp_path/'bad.step'
    path.write_bytes(content)
    with pytest.raises((ValueError, RuntimeError)):
        inspect_step_geometry(path)


def test_timeout_kills_readback_process(tmp_path):
    marker = tmp_path/'finished'
    argv = [sys.executable, '-c', 'import time,pathlib,sys;time.sleep(10);pathlib.Path(sys.argv[1]).touch()', str(marker)]
    start = time.monotonic()
    assert run_bounded(argv, tmp_path/'timeout.log', timeout=0.15) == 124
    assert time.monotonic() - start < 5 and not marker.exists()


def test_nonzero_process_is_not_success(tmp_path):
    assert run_bounded([sys.executable, '-c', 'raise SystemExit(7)'], tmp_path/'exit.log') == 7


def test_configuration_cannot_execute_commands(tmp_path):
    cases = tmp_path/'cases.json'
    cases.write_text(json.dumps({'cases':[]}))
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'command':['touch','injected']}))
    with pytest.raises(ValueError, match='configuration'):
        probe(cases, config, tmp_path/'output')


def test_shared_b01_config_preserved_and_private_fields_omitted(tmp_path):
    config = tmp_path/'config.json'
    original = json.dumps(dict(dwg={'adapter':'existing'}, work_root='/existing', native=dict(
        adapter=None, endpoint_or_executable='private-endpoint', vendors=[], timeout_s=600,
        credential_ref='private-reference')))
    config.write_text(original)
    assert load_native_config(config) == {'adapter':None}
    assert config.read_text() == original
