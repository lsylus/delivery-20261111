"""Bind B11 to actual B10 full acceptance, immutable archive and independent review."""
import json,hashlib,subprocess
from pathlib import Path
from check_b10_prerequisites import historical_fingerprint
ROOT=Path(__file__).resolve().parents[1]
DELIVERY='b1a22a0c090717f92cf8db7f9cb09b12becfe7b1'
BASE='f975be122691003efee1d0f8c2ce96a92c393d7c'
TESTED='5e7a839c727f0d16df2c7be8d5d075c6190ec43a'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()
def audit():
    for a,b in [(TESTED,DELIVERY),(DELIVERY,BASE),(BASE,'HEAD')]:git('merge-base','--is-ancestor',a,b)
    assert all(n.startswith('docs/') for n in git('diff','--name-only',DELIVERY,BASE).decode().splitlines())
    review=json.loads((ROOT/'docs/evidence/B10/review/independent-review.json').read_text())
    assert review['decision']=='approved' and review['full_acceptance'] is True and review['scope']=='B10-full'
    assert review['tested_revision']==TESTED and review['delivery_revision']==DELIVERY
    assert historical_fingerprint(ROOT,TESTED)==historical_fingerprint(ROOT,DELIVERY)==historical_fingerprint(ROOT,BASE)==review['source_fingerprint']
    a=json.loads((ROOT/'docs/evidence/B10/archive-hashes.json').read_text())
    for f in a['files']:
        b=git('show',DELIVERY+':'+f['path']);assert sha(b)==f['sha256'] and len(b)==f['bytes'],f['path']
        # Reviewed documentation changed in its own commits; evidence bytes did not.
        if f['path'].startswith('docs/evidence/'):assert (ROOT/f['path']).read_bytes()==b,f['path']
    for f in review['evidence']:assert sha((ROOT/f['path']).read_bytes())==f['sha256'],f['path']
    hashes=(ROOT/'docs/evidence/B10/review/review-hashes.txt').read_text().splitlines()
    for line in hashes:
        h,p=line.split(None,1);assert sha((ROOT/p.strip()).read_bytes())==h,p
    summaries=[]
    for path in ['docs/evidence/B10/summary.json','docs/evidence/B10/review/runner/summary.json']:
        x=json.loads((ROOT/path).read_text())
        assert x['status']=='passed' and x['dirty'] is False and x['tests']==dict(required=63,passed=63,failed=0,skipped_required=0)
        assert all(c['exit_code']==0 for c in x['commands']) and all(c['status']=='pass' for c in x['checks'])
        summaries.append(dict(path=path,sha256=sha((ROOT/path).read_bytes()),tests=x['tests']))
    consumed=['service/src/thermal_drawings/blanket/'+p+'.py' for p in ['selection','baseline','allowance','surfaces','openings','volume','checks','pipeline']]
    for p in consumed:assert (ROOT/p).read_bytes()==git('show',TESTED+':'+p),p
    assert json.loads((ROOT/'docs/evidence/B09/summary.json').read_text())['status']=='blocked'
    return dict(status='pass',delivery=DELIVERY,baseline=BASE,tested=TESTED,archive_hashes=len(a['files']),review_hashes=len(hashes),summaries=summaries,unchanged_consumed_interfaces=consumed,independent_review_sha256=sha((ROOT/'docs/evidence/B10/review/independent-review.json').read_bytes()),source_fingerprint=review['source_fingerprint'],retained=review['retained_external_final_blockers'])
if __name__=='__main__':
    result=audit();out=ROOT/'docs/evidence/B11';out.mkdir(parents=True,exist_ok=True);(out/'prerequisites.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
