import copy
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_b10_prerequisites import check_development,POLICY
from verify_batch import verify


@pytest.mark.parametrize('batch,rule',[('B09',dict(summary='docs/evidence/B09/summary.json',development_policy=POLICY)),('B11',dict(summary='docs/evidence/B09/summary.json',development_policy=POLICY)),('B10',dict(summary='docs/evidence/B07/summary.json',development_policy=POLICY)),('B10',dict(summary='docs/evidence/B09/summary.json',development_policy='ignore-blocked'))])
def test_development_consumption_is_explicitly_limited(batch,rule,tmp_path):
    with pytest.raises(AssertionError):check_development(tmp_path,batch,rule)


@pytest.mark.parametrize('change',['blocked','dirty','skip','full','commands','review'])
def test_corrupted_or_unapproved_development_cannot_be_consumed(tmp_path,change):
    target=tmp_path/'docs/evidence/B09';target.mkdir(parents=True)
    dev=json.loads((ROOT/'docs/evidence/B09/development.json').read_text())
    review=json.loads((ROOT/'docs/evidence/B09/independent-review.json').read_text())
    if change=='blocked':dev['status']='blocked'
    elif change=='dirty':dev['dirty']=True
    elif change=='skip':dev['tests']['skipped_required']=1
    elif change=='full':dev['full_acceptance']=True
    elif change=='commands':dev['commands'][0]['exit_code']=1
    else:review['decision']='pending'
    (target/'development.json').write_text(json.dumps(dev));(target/'independent-review.json').write_text(json.dumps(review))
    with pytest.raises(AssertionError):
        check_development(tmp_path,'B10',dict(summary='docs/evidence/B09/summary.json',development_policy=POLICY))


def test_b09_full_gate_still_actually_returns_blocked_without_rewriting_original(tmp_path):
    out=ROOT/'work/b10-final-gate-test';out.mkdir(parents=True,exist_ok=True)
    before=(ROOT/'docs/evidence/B09/summary.json').read_bytes()
    assert verify('B09',out,ROOT)==2
    value=json.loads((out/'summary.json').read_text())
    assert value['status']=='blocked' and value['tests']['required']==0
    assert (ROOT/'docs/evidence/B09/summary.json').read_bytes()==before
