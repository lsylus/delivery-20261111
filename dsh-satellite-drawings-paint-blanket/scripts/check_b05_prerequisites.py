"""B05 depends only on the accepted B02 implementation and evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = '17728459da21e7c269ef709ec0ebd6c3c6e3b604'


def main():
    raw = (ROOT / 'docs/evidence/B02/summary.json').read_bytes()
    summary = json.loads(raw)
    assert summary['status'] == 'passed' and summary['dirty'] is False
    assert summary['code_revision'] == REVISION
    assert summary['tests'] == dict(required=109, passed=109, failed=0, skipped_required=0)
    assert all(c['exit_code'] == 0 for c in summary['commands'])
    assert all(c['status'] == 'pass' for c in summary['checks'])
    subprocess.run(['git', 'merge-base', '--is-ancestor', REVISION, 'HEAD'], cwd=ROOT, check=True)
    review = (ROOT / 'docs/reviews/B02.md').read_bytes()
    assert '结论：**PASS**' in review.decode('utf-8')
    checked = []
    for item in summary['inputs'] + summary['artifacts']:
        path = item['path']
        origin = 'archive' if path.startswith('docs/evidence/') else 'tested_commit'
        data = (ROOT / path).read_bytes() if origin == 'archive' else subprocess.check_output(
            ['git', 'show', f'{REVISION}:{path}'], cwd=ROOT)
        assert hashlib.sha256(data).hexdigest() == item['sha256'] and len(data) == item['bytes'], path
        checked.append(dict(item, verified_against=origin))
    interfaces = {}
    for name in ['common', 'model', 'mesh-map']:
        path = f'contracts/{name}.schema.json'
        data = subprocess.check_output(['git', 'show', f'{REVISION}:{path}'], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        old, new = json.loads(data), json.loads(current)
        # Accepted B06 extensions are outside native input / B02 model geometry.
        if name == 'common':
            added = new['$defs']['Artifact']['properties'].pop('download_url', None)
            assert added == {'type': 'string', 'pattern': '^/api/v1/artifacts/[a-f0-9]{32}$'}
        if name == 'model':
            properties = new['$defs']['EngineeringBundle']['properties']
            assert properties['drawing_document'] == {'anyOf': [
                {'$ref': 'drawing.schema.json#/$defs/DrawingDocument'}, {'type': 'null'}]}
            properties['drawing_document'] = old['$defs']['EngineeringBundle']['properties']['drawing_document']
        assert new == old, path
        interfaces[name] = dict(b02_sha256=hashlib.sha256(data).hexdigest(),
                               current_sha256=hashlib.sha256(current).hexdigest(), compatible=True)
    # The actual B02 reader closure must still be the accepted implementation.
    for item in summary['artifacts']:
        if item['path'].startswith('packages/geometry-core/src/'):
            assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    out = ROOT / 'docs/evidence/B05'
    out.mkdir(parents=True, exist_ok=True)
    result = dict(status='pass', b02_revision=REVISION,
                  summary_sha256=hashlib.sha256(raw).hexdigest(),
                  review_sha256=hashlib.sha256(review).hexdigest(), checked=checked,
                  interfaces=interfaces, dependency_scope=['B02'])
    (out / 'prerequisites.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'B02 verified: {len(checked)} hashes, 109/109, clean acceptance, ancestor, interfaces, reader closure')


if __name__ == '__main__':
    main()
