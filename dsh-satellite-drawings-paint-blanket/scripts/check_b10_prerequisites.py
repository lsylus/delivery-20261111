"""B10 alone may consume the independently approved B09 development scope."""
import hashlib
import json
from pathlib import Path
import subprocess
from verify_batch import prerequisite_artifact_matches, safe, sha

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'B10-consumes-B09-development-v1'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def historical_fingerprint(root, revision):
    roots = ('service/', 'packages/', 'plugins/', 'contracts/', 'scripts/', 'tests/', 'fixtures/')
    configs = {'package.json', 'package-lock.json', 'playwright.b09.config.ts', 'playwright.b12.config.ts', 'tsconfig.b07.json', 'pyproject.toml', 'uv.lock'}
    names = sorted(n for n in git(root, 'ls-tree', '-r', '--name-only', revision).decode().splitlines() if n.startswith(roots) or n in configs)
    return hashlib.sha256(json.dumps([(n, hashlib.sha256(git(root, 'show', f'{revision}:{n}')).hexdigest()) for n in names], separators=(',', ':')).encode()).hexdigest()


def check_development(root, batch, rule):
    # No wildcard bypass and no alternate registry-selected evidence or policy.
    assert batch == 'B10' and rule == {'summary': 'docs/evidence/B09/summary.json', 'development_policy': POLICY}
    dev = json.loads((root/'docs/evidence/B09/development.json').read_text())
    review = json.loads((root/'docs/evidence/B09/independent-review.json').read_text())
    assert review['decision'] == 'approved' and review['scope'] == 'B09-development' and review['reviewer'] and review['full_acceptance'] is False
    assert dev['status'] == dev['scope_tests_status'] == 'passed' and dev['full_acceptance'] is False and dev['dirty'] is False
    assert dev['tests']['required'] == dev['tests']['passed'] > 0 and dev['tests']['failed'] == dev['tests']['skipped_required'] == 0
    assert len(dev['commands']) == 12 and all(c['exit_code'] == 0 and sha(safe(root,c['log_ref'])) == c['log_sha256'] for c in dev['commands'])
    assert dev['checks'] and all(c['status'] == 'pass' for c in dev['checks']) and not dev['missing_test_files']
    assert dev['independent_review']['status'] == 'passed'
    for revision in (dev['code_revision'], review['code_revision']):
        git(root, 'merge-base', '--is-ancestor', revision, 'HEAD')
        assert historical_fingerprint(root, revision) == dev['code_fingerprint'] == review['code_fingerprint']
    superseded = []
    metadata = {'docs/evidence/B09/archive-hashes.json', 'docs/evidence/B09/final-exit.json', 'docs/evidence/B09/development-exit.json'}
    for item in dev['artifacts'] + review['evidence_refs']:
        p = safe(root, item['path'])
        if item['path'] in metadata and sha(p) != item['sha256']:
            old = git(root, 'show', f"{dev['code_revision']}:{item['path']}")
            assert hashlib.sha256(old).hexdigest() == item['sha256'] and len(old) == item['bytes']
            superseded.append(dict(path=item['path'], historical_sha256=item['sha256'], current_sha256=sha(p), reason='Post-run receipt/archive metadata; original bytes verified at development start commit'))
            continue
        assert p.is_file() and sha(p) == item['sha256'], item['path']
        if 'bytes' in item:
            assert p.stat().st_size == item['bytes'], item['path']
    assert len(dev['missing_acceptance']) == 4 and len(review['retained_final_blockers']) == 4
    receipt=json.loads((root/'docs/evidence/B09/development-exit.json').read_text())
    assert receipt['exit_code']==0 and receipt['dirty_at_start'] is False and receipt['development_sha256']==sha(root/'docs/evidence/B09/development.json')
    receipt=json.loads((root/'docs/evidence/B09/final-exit.json').read_text())
    assert receipt['exit_code']==2 and receipt['status']=='blocked' and receipt['summary_sha256']==sha(root/'docs/evidence/B09/summary.json')
    # These exact consumed geometry, auth, validation and paint interfaces remain
    # byte-identical. B10 runtime dispatch extensions are tested by B10 regression.
    prefixes = ('packages/geometry-core/', 'service/src/thermal_drawings/paint/', 'service/src/thermal_drawings/drawing/',
                'service/src/thermal_drawings/api/auth.py', 'service/src/thermal_drawings/domain/validation.py',
                'service/src/thermal_drawings/runtime/queue.py', 'service/src/thermal_drawings/runtime/recovery.py')
    names = [n for n in git(root, 'ls-tree', '-r', '--name-only', review['code_revision']).decode().splitlines() if n.startswith(prefixes)]
    for n in names:
        assert (root/n).read_bytes() == git(root, 'show', f"{review['code_revision']}:{n}"), n
    return dict(policy=POLICY, status='pass', reviewed_revision=review['code_revision'], development_revision=dev['code_revision'],
                fingerprint=dev['code_fingerprint'], verified_artifacts=len(dev['artifacts']), unchanged_consumed_interfaces=names,
                development_sha256=sha(root/'docs/evidence/B09/development.json'), review_sha256=sha(root/'docs/evidence/B09/independent-review.json'),
                full_acceptance=False, retained=dev['missing_acceptance'], superseded_metadata=superseded)


def audit(root=ROOT):
    records = []
    for batch, count in (('B02',109), ('B06',104)):
        path=root/f'docs/evidence/{batch}/summary.json'; data=json.loads(path.read_text())
        assert data['status']=='passed' and data['dirty'] is False
        assert data['tests']==dict(required=count,passed=count,failed=0,skipped_required=0)
        assert all(c['exit_code']==0 for c in data['commands']) and all(c['status']=='pass' for c in data['checks'])
        git(root,'merge-base','--is-ancestor',data['code_revision'],'HEAD')
        for item in data['inputs']+data['artifacts']:
            assert prerequisite_artifact_matches(root,data['code_revision'],item),item['path']
        assert '**PASS**' in (root/f'docs/reviews/{batch}.md').read_text()
        records.append(dict(batch=batch,revision=data['code_revision'],summary_sha256=sha(path),verified_hashes=len(data['inputs'])+len(data['artifacts'])))
    return dict(status='pass',batches=records,development=check_development(root,'B10',dict(summary='docs/evidence/B09/summary.json',development_policy=POLICY)))


if __name__ == '__main__':
    result=audit(); out=ROOT/'docs/evidence/B10';out.mkdir(parents=True,exist_ok=True)
    (out/'prerequisites.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],batches=result['batches'],b09_artifacts=result['development']['verified_artifacts'])))
