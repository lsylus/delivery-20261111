import sys,json,hashlib
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from verify_b12_development import review_check
from verify_development import assess
from check_b12_prerequisites import check_development,POLICY
@pytest.mark.parametrize('batch,rule',[('B13',{'summary':'docs/evidence/B09/summary.json','development_policy':POLICY}),('B12',{'summary':'docs/evidence/B07/summary.json','development_policy':POLICY}),('B12',{'summary':'docs/evidence/B09/summary.json','development_policy':'ignore-blocked'}),('B12',{'summary':'docs/evidence/B09/summary.json','development_policy':POLICY,'ignore':True})])
def test_policy_cannot_consume_other_batches_or_generic_blocked(tmp_path,batch,rule):
 with pytest.raises(AssertionError):check_development(tmp_path,batch,rule)
def test_b12_review_is_exact_scope_revision_and_hash(tmp_path):
 out=tmp_path/'docs/evidence/B12';out.mkdir(parents=True);e=tmp_path/'evidence';e.write_text('independent observation');r=dict(decision='approved',scope='B12-development',full_acceptance=False,reviewer='unit-test reviewer only',code_revision='a'*40,code_fingerprint='b'*64,evidence_refs=[dict(path='evidence',sha256=hashlib.sha256(e.read_bytes()).hexdigest())]);p=out/'independent-review.json';p.write_text(json.dumps(r))
 assert review_check(tmp_path,'a'*40,'b'*64)
 for key,value in [('scope','B09-development'),('full_acceptance',True),('code_fingerprint','c'*64)]:p.write_text(json.dumps(dict(r,**{key:value})));assert not review_check(tmp_path,'a'*40,'b'*64)
 p.write_text(json.dumps(r));e.write_text('tampered');assert not review_check(tmp_path,'a'*40,'b'*64)
def test_b12_implementation_cannot_approve_its_own_development():
 assert assess([dict(exit_code=0)],dict(required=1,passed=1,failed=0,skipped_required=0),[dict(status='pass')],[],False)=='blocked'
def test_full_b12_entry_retains_all_original_prerequisites_and_external_evidence():
 root=Path(__file__).resolve().parents[2];entry=json.loads((root/'scripts/batches.json').read_text())['B12']
 assert entry['prerequisites']==[dict(summary=f'docs/evidence/{b}/summary.json') for b in ['B04','B07','B11']]
 assert len(entry['manual_evidence'])==3

def test_blanket_selection_schema_matches_real_host_wire_context():
 from contracts import validate
 root=Path(__file__).resolve().parents[2];value=json.loads((root/'fixtures/contracts/blanket-selection.json').read_text())
 validate('operation',value,'SelectionContext')
 value['blanket_target']['edges'][0]['world']=[[]]
 with pytest.raises(Exception):validate('operation',value,'SelectionContext')
