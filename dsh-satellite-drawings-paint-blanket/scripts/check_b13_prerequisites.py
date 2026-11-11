"""B13 exact consumption of B09/B12 approvals; no generic blocked exemption."""
import hashlib,json,os,subprocess
from pathlib import Path
from check_b12_prerequisites import historical_fingerprint
from verify_batch import safe,sha
ROOT=Path(__file__).resolve().parents[1]
BASE='6202bc2d7cae50b969ef358ecf4672a5ba1ea79b'
POLICY={'batch':'B13','policy':'B13-consumes-B09-B12-development-v1',
        'B09':'docs/evidence/B09/development.json','B12':'docs/evidence/B12/review/final-run/development.json'}
def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)
def verify(root,item,revision=None):
    b=git(root,'show',revision+':'+item['path']) if revision else safe(root,item['path']).read_bytes()
    assert hashlib.sha256(b).hexdigest()==item['sha256'],item['path']
    if 'bytes' in item:assert len(b)==item['bytes'],item['path']
def audit(root=ROOT,policy=None):
    assert (POLICY if policy is None else policy)==POLICY
    git(root,'merge-base','--is-ancestor',BASE,'HEAD')
    records=[]
    for batch,count in [('B09',12),('B12',11)]:
        path=POLICY[batch];dev=json.loads((root/path).read_text())
        review_path=f'docs/evidence/{batch}/independent-review.json';review=json.loads((root/review_path).read_text())
        assert review['decision']=='approved' and review['scope']==batch+'-development' and review['full_acceptance'] is False and review['reviewer']
        assert dev['status']==dev['scope_tests_status']=='passed' and dev['full_acceptance'] is False and dev['dirty'] is False
        assert dev['tests']['required']==dev['tests']['passed']>0 and dev['tests']['failed']==dev['tests']['skipped_required']==0
        assert not dev['missing_test_files'] and dev['independent_review']['status']=='passed'
        assert len(dev['commands'])==count and all(c['exit_code']==0 and sha(safe(root,c['log_ref']))==c['log_sha256'] for c in dev['commands'])
        assert all(c['status']=='pass' for c in dev['checks']) and dev['checks']
        for revision in (review['code_revision'],dev['code_revision']):
            git(root,'merge-base','--is-ancestor',revision,'HEAD')
            assert historical_fingerprint(root,revision)==dev['code_fingerprint']==review['code_fingerprint']
        for item in review['evidence_refs']:verify(root,item)
        superseded=[]
        for item in dev['artifacts']:
            if batch=='B09' and item['path'] in {'docs/evidence/B09/archive-hashes.json','docs/evidence/B09/final-exit.json','docs/evidence/B09/development-exit.json'} and sha(safe(root,item['path']))!=item['sha256']:
                verify(root,item,dev['code_revision']);superseded.append(item['path'])
            else:verify(root,item)
        assert len(dev['missing_acceptance'])==len(review['retained_final_blockers'])==4
        records.append(dict(batch=batch,approval_sha256=sha(root/review_path),development_sha256=sha(root/path),tested_revision=review['code_revision'],
                            fingerprint=review['code_fingerprint'],commands=count,artifacts=len(dev['artifacts']),superseded_metadata=superseded))
    receipt=json.loads((root/'docs/evidence/B09/development-exit.json').read_text())
    assert receipt['exit_code']==0 and receipt['dirty_at_start'] is False and receipt['development_sha256']==sha(root/POLICY['B09'])
    receipt=json.loads((root/'docs/evidence/B09/final-exit.json').read_text())
    assert receipt['exit_code']==2 and receipt['status']=='blocked' and receipt['summary_sha256']==sha(root/'docs/evidence/B09/summary.json')
    receipt=json.loads((root/'docs/evidence/B12/review/final-run-verification.json').read_text())
    assert receipt['native_exit_code']==0 and receipt['approval_commit']=='aa1422880925b36b509264f5c8fa87c9fd310cce'
    for item in receipt['evidence']+receipt['preserved_attempts']:verify(root,item)
    assert receipt['preserved_attempts'][0]['native_exit_code']==2 and receipt['preserved_attempts'][0]['scope_tests_status']=='passed'
    # Original full acceptance receipts remain required, never rewritten.
    full=json.loads((root/'docs/evidence/B12/full-exit.json').read_text())
    assert full['exit_code']==2 and full['status']=='blocked' and full['dirty_at_start'] is False and full['original_b09_summary_unchanged'] is True
    assert full['original_b09_summary_sha256']==sha(root/'docs/evidence/B09/summary.json')
    assert json.loads((root/'docs/evidence/B12/summary.json').read_text())['status']=='blocked'
    archive=json.loads(git(root,'show',BASE+':docs/evidence/B12/review/final-review-files.json'))
    for item in archive['entries']:verify(root,item,BASE)
    # Existing consumed interfaces at the integration base are bound to the
    # reviewed bytes. B13 changes are subsequently subject to its own tests/review.
    changed=git(root,'diff','--name-only','d8ff227eba30f08c293387f023a6a9e07d95bbd4',BASE).decode().splitlines()
    assert changed and all(p.startswith('docs/') for p in changed)
    return dict(schema_version=1,status='pass',policy=POLICY,baseline=BASE,full_acceptance=False,approvals=records,
                historical_review_files=len(archive['entries']),retained=['B04 AutoCAD','B05 native','B07 formal DSH','B09/B12 full blocked','B12 complete assembly triangulation failure','B13 case-specific manufacturing criteria'])
if __name__=='__main__':
    result=audit();out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13');out.mkdir(parents=True,exist_ok=True)
    (out/'prerequisites.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
