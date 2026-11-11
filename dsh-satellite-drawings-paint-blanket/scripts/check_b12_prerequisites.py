"""B12 alone may consume the independently approved B09 development scope."""
import hashlib
import json
from pathlib import Path
import subprocess
from verify_batch import prerequisite_artifact_matches, safe, sha

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'B12-consumes-B09-development-v1'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def historical_fingerprint(root, revision):
    roots = ('service/', 'packages/', 'plugins/', 'contracts/', 'scripts/', 'tests/', 'fixtures/')
    configs = {'package.json', 'package-lock.json', 'playwright.b09.config.ts', 'playwright.b12.config.ts', 'playwright.b13.config.ts', 'tsconfig.b07.json', 'pyproject.toml', 'uv.lock'}
    names = sorted(n for n in git(root, 'ls-tree', '-r', '--name-only', revision).decode().splitlines() if n.startswith(roots) or n in configs)
    return hashlib.sha256(json.dumps([(n, hashlib.sha256(git(root, 'show', f'{revision}:{n}')).hexdigest()) for n in names], separators=(',', ':')).encode()).hexdigest()


def check_development(root, batch, rule):
    # No wildcard bypass and no alternate registry-selected evidence or policy.
    assert batch == 'B12' and rule == {'summary': 'docs/evidence/B09/summary.json', 'development_policy': POLICY}
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


BASE='f0771fcb1549258248ca563920a7462f511d32da'
def audit(root=ROOT):
    git(root,'merge-base','--is-ancestor',BASE,'HEAD')
    review=json.loads((root/'docs/evidence/B11/review/independent-review.json').read_text())
    assert review['decision']=='approved' and review['scope']=='B11-full' and review['full_acceptance'] is True
    assert review['source_fingerprint']=='6698a391fc69391cfef21bbd8a8a4009ee3f0478cbfa9b550076a8aa151fd577'
    for revision in (review['tested_revision'],review['delivery_revision'],BASE):
        assert historical_fingerprint(root,revision)==review['source_fingerprint'];git(root,'merge-base','--is-ancestor',revision,'HEAD')
    for item in review['evidence']:
        path=safe(root,item['path']);assert sha(path)==item['sha256'] and path.stat().st_size==item['bytes'],item['path']
    for line in (root/'docs/evidence/B11/review/review-hashes.txt').read_text().splitlines():
        h,p=line.split(None,1);assert sha(safe(root,p.strip()))==h,p
    archives={}
    for rev in (review['archive_revision'],review['delivery_revision']):
        archive=json.loads(git(root,'show',rev+':docs/evidence/B11/archive-hashes.json'))
        for item in archive['files']:
            b=git(root,'show',rev+':'+item['path']);assert hashlib.sha256(b).hexdigest()==item['sha256'] and len(b)==item['bytes'],item['path']
        archives[rev]=len(archive['files'])
    summaries=[]
    for name in ['docs/evidence/B11/summary.json','docs/evidence/B11/review/runner/summary.json']:
        d=json.loads((root/name).read_text());assert d['status']=='passed' and d['dirty'] is False
        assert d['tests']==dict(required=60,passed=60,failed=0,skipped_required=0)
        assert all(c['exit_code']==0 for c in d['commands']) and all(c['status']=='pass' for c in d['checks'])
        for item in d['inputs']+d['artifacts']:
            path=item['path']
            if path.startswith('docs/evidence/'):
                if '/review/' in name:path=path.replace('docs/evidence/B11/','docs/evidence/B11/review/generated/',1)
                b=safe(root,path).read_bytes()
            else:b=git(root,'show',d['code_revision']+':'+path)
            assert hashlib.sha256(b).hexdigest()==item['sha256'],path
        summaries.append(dict(path=name,sha256=sha(root/name),tests=d['tests']))
    b09=check_development(root,'B12',dict(summary='docs/evidence/B09/summary.json',development_policy=POLICY))
    consumers=[]
    for batch in ['B04','B07']:
        p=root/f'docs/evidence/{batch}/summary.json';d=json.loads(p.read_text());assert d['status']=='blocked' and d['dirty'] is False
        assert d['tests']['required']==d['tests']['passed']>0 and not d['tests']['skipped_required']
        git(root,'merge-base','--is-ancestor',d['code_revision'],'HEAD')
        mismatches=[x['path'] for x in d['artifacts'] if not prerequisite_artifact_matches(root,d['code_revision'],x)]
        assert set(mismatches)<=({'.gitignore'} if batch=='B07' else set())
        consumers.append(dict(batch=batch,full_status=d['status'],summary_sha256=sha(p),artifact_count=len(d['artifacts']),historical_unconsumed_mismatches=mismatches))
    conversion=json.loads((root/'docs/evidence/B04/conversion.json').read_text());assert conversion['capability']['real_conversion_verified'] and all(c['exit_code']==0 for c in conversion['commands'])
    browser=json.loads((root/'docs/evidence/B07/browser-acceptance.json').read_text());assert browser['status']=='pass' and browser['counts']['passed']>0 and browser['counts']['failed']==browser['counts']['skipped']==0
    assert json.loads((root/'docs/evidence/B09/summary.json').read_text())['status']=='blocked'
    return dict(status='pass',policy=POLICY,full_acceptance=False,baseline=BASE,b11_summaries=summaries,b11_archives=archives,b11_review_sha256=sha(root/'docs/evidence/B11/review/independent-review.json'),b09=b09,consumed=consumers,retained=['B04 AutoCAD','B05 native ASM/PRT','B07 formal DSH','manufacturing human review'])

if __name__=='__main__':
    import os
    out=ROOT/os.environ.get('B12_EVIDENCE_DIR','docs/evidence/B12');out.mkdir(parents=True,exist_ok=True)
    result=audit();(out/'prerequisites.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],policy=POLICY,b11_archives=result['b11_archives'])))
