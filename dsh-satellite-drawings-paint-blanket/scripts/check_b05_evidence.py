"""Audit independent deliverables while keeping the real native acceptance gate blocked."""
import json
from pathlib import Path
from collections import Counter
from contracts import validate
from thermal_drawings.importers.manifest import sha, verify_manifest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/evidence/B05'


def dump(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def main():
    report = json.loads((OUT/'conversion-report.json').read_text())
    cases = json.loads((ROOT/'fixtures/manifests/native_cases.json').read_text())['cases']
    assert {c['id'] for c in cases} == {c['id'] for c in report['cases']}
    index = json.loads((OUT/'Star1-inventory.json').read_text())
    baseline = json.loads((ROOT/'fixtures/manifests/Star1.inventory.json').read_text())
    fingerprints = lambda items: {f['relative_path']:(f['sha256'],f['bytes']) for f in items}
    assert fingerprints(index['files']) == fingerprints(baseline['files'])
    for case in report['cases']:
        path = OUT/case['manifest_ref']
        assert sha(path) == case['manifest_sha256']
        bundle = json.loads(path.read_text())
        validate('model',bundle['source_manifest'],'SourceManifest')
        verify_manifest(bundle['source_root'],bundle['source_manifest'])
        assert bundle['dependency_report']['complete'] is False
        assert bundle['source_manifest']['load_status'] == 'not_opened'
        assert case['step_asset'] is None and case['native_process_exit'] is None
        assert case['status'] == 'blocked' and case['capability']['available'] is False
    assert report['resources_created'] == report['resources_cleaned']
    assert all(not Path(p).exists() for p in report['resources_cleaned'])
    assert report['all_source_inventories_unchanged'] is True
    old = report['historical_step']
    assert old['exit_code'] == 1 and old['readback']['status'] == 'failed'
    assert old['readback']['error_type'] == 'StepReadError'
    assert 'no transferable roots' in old['readback']['reason']
    assert report['conversions_executed'] == 0
    dump('scope-checks.json', dict(status='pass', scope='inventory/detection/integrity/negative-readback only',
        star1_baseline_files_verified=len(index['files']),
        detected_counts=dict(Counter(f['detection']['detected_format'] for f in index['files'])),
        native_manifests_validated=len(cases), historical_empty_step_rejected=True,
        resources_cleaned=report['resources_cleaned'], sources_unchanged=True))
    dump('native-acceptance.json', dict(status='blocked', real_conversions_executed=0,
        required=[dict(scope='Creo real geometric part',status='blocked'),
                  dict(scope='Creo complete small assembly',status='blocked')],
        actual_geometry_comparison=None, actual_units_comparison=None,
        actual_dependency_closure=None, actual_transform_comparison=None,
        reason='No configured authorized Creo/SDK execution endpoint; no engine-specific adapter selected',
        recovery=['Provide authorized Creo capable of loading 9.0.8.0 or a licensed SDK with documented version coverage',
                  'Register its actual loader/export API; implement and test only that adapter, with process isolation and bounded execution',
                  'Load isolated copies, collect actual dependencies/suppression/family-table status and native geometry/tree/placements/units',
                  'Export real part and complete assembly to STEP; compare B02 readback with native facts and recorded case tolerances',
                  'Run B05 from clean tested commit and independently review; NX requires separate real vendor-specific acceptance if in final scope'],
        unaffected='B02 STEP path and independent work remain available; B14/B15 full native delivery remains blocked. B04/B07 gates unchanged'))
    print('Independent checks passed; native acceptance remains blocked')


if __name__ == '__main__':
    main()
