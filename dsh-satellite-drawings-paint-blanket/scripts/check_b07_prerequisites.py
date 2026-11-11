"""Revalidate accepted B06/B08 commits, interfaces and archived assets before B07."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evidence/B07'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    records = {}
    for batch, review_commit in [('B06', 'd812f72'), ('B08', '24d4b049756507c4188b6c11eb0b6b91069a9d6d')]:
        raw = (ROOT / f'docs/evidence/{batch}/summary.json').read_bytes()
        summary = json.loads(raw)
        assert summary['status'] == 'passed' and not summary['dirty']
        assert summary['tests']['required'] == summary['tests']['passed'] > 0
        assert summary['tests']['failed'] == summary['tests']['skipped_required'] == 0
        assert all(c['exit_code'] == 0 for c in summary['commands'])
        assert all(c['status'] == 'pass' for c in summary['checks'])
        review = (ROOT / f'docs/reviews/{batch}.md').read_bytes()
        assert '结论：**PASS**' in review.decode()
        for rev in (summary['code_revision'], review_commit):
            subprocess.run(['git', 'merge-base', '--is-ancestor', rev, 'HEAD'], cwd=ROOT, check=True)
        entries = []
        for item in summary['inputs'] + summary['artifacts']:
            path = item['path']
            if path.startswith('docs/evidence/'):
                data = (ROOT / path).read_bytes()
                origin = 'archive'
            else:
                p = subprocess.run(['git', 'show', summary['code_revision'] + ':' + path], cwd=ROOT, capture_output=True)
                data = p.stdout if p.returncode == 0 else (ROOT / path).read_bytes()
                origin = 'tested_commit' if p.returncode == 0 else 'archive'
            assert digest(data) == item['sha256'] and len(data) == item['bytes'], path
            entries.append(dict(**item, origin=origin))
        records[batch] = dict(status='pass', code_revision=summary['code_revision'],
                             review_commit=subprocess.check_output(['git', 'rev-parse', review_commit], cwd=ROOT, text=True).strip(),
                             summary_sha256=digest(raw), review_sha256=digest(review), entries=entries)
    provenance = json.loads((ROOT / 'docs/evidence/B03/source-provenance.json').read_text())
    for item in provenance['sources'] + provenance['inputs']:
        data = Path(item['path']).read_bytes()
        assert digest(data) == item['sha256'] and len(data) == item['bytes']
    interfaces = {}
    for name in ('common', 'model', 'mesh-map', 'paint', 'operation', 'runtime'):
        data = subprocess.check_output(['git','show',f'24d4b04:contracts/{name}.schema.json'], cwd=ROOT)
        assert data == (ROOT/f'contracts/{name}.schema.json').read_bytes(), name
        interfaces[name] = dict(schema_id=json.loads(data)['$id'], sha256=digest(data))
    assert json.loads((ROOT/'docs/evidence/B04/summary.json').read_text())['status'] == 'blocked'
    assert '**FAIL**' in (ROOT/'docs/reviews/B04.md').read_text()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'prerequisites.json').write_text(json.dumps(dict(status='pass', batches=records, interfaces_at_start=interfaces,
        b03_external_files_verified=len(provenance['sources']+provenance['inputs']),
        boundary='B04 blocked/FAIL; final AutoCAD open/edit/save/reopen gate retained'), indent=2)+'\n')
    print({b: len(r['entries']) for b,r in records.items()})

if __name__ == '__main__':
    main()
