import sys,copy,json,hashlib,subprocess
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from verify_development import assess,review_check,code_fingerprint,TESTS,TEST_GROUPS
COUNTS=dict(required=3,passed=3,failed=0,skipped_required=0)
def test_review_is_required_even_when_scoped_checks_pass():
 assert assess([{'exit_code':0}],COUNTS,[{'status':'pass'}],[],False)=='blocked'
 assert assess([{'exit_code':0}],COUNTS,[{'status':'pass'}],[],True)=='passed'
@pytest.mark.parametrize('counts,commands,checks,missing,expected',[
 (dict(required=0,passed=0,failed=0,skipped_required=0),[{'exit_code':0}],[],[],'blocked'),
 (dict(COUNTS,passed=2,skipped_required=1),[{'exit_code':0}],[],[],'blocked'),
 (dict(COUNTS,passed=2,failed=1),[{'exit_code':0}],[],[],'failed'),
 (COUNTS,[{'exit_code':3}],[],[],'failed'),
 (COUNTS,[{'exit_code':0}],[{'status':'fail'}],[],'failed'),
 (COUNTS,[{'exit_code':0}],[],['unexecuted.py'],'blocked'),
])
def test_no_empty_skip_or_external_excuse_for_development_failure(counts,commands,checks,missing,expected):
 assert assess(commands,counts,checks,missing,True)==expected
def test_review_requires_exact_code_and_hashed_evidence(tmp_path):
 out=tmp_path/'docs/evidence/B09';out.mkdir(parents=True);report=tmp_path/'review.md';report.write_text('Independent test review')
 record=dict(decision='approved',scope='B09-development',reviewer='test reviewer',code_revision='a'*40,code_fingerprint='b'*64,evidence_refs=[dict(path='review.md',sha256=hashlib.sha256(report.read_bytes()).hexdigest())])
 (out/'independent-review.json').write_text(json.dumps(record));assert review_check(tmp_path,'a'*40,'b'*64)
 assert not review_check(tmp_path,'c'*40,'b'*64)
 report.write_text('tampered');assert not review_check(tmp_path,'a'*40,'b'*64)
def test_final_batch_gate_still_requires_blocked_prerequisites():
 from verify_batch import assess as final_assess
 assert final_assess(COUNTS,[{'exit_code':0}],[{'status':'blocked'}])=='blocked'

def test_grouped_collection_covers_every_required_test_exactly_once():
 grouped=[path for group in TEST_GROUPS for path in group]
 assert sorted(grouped)==sorted(TESTS) and len(grouped)==len(set(grouped))
 assert all(not(any(p.startswith('tests/runtime/') for p in g) and any(p.startswith('tests/paint/') for p in g)) for g in TEST_GROUPS)

def test_source_fingerprint_ignores_rebuilt_outputs_but_detects_source_edits(tmp_path):
 subprocess.run(['git','init','-q',str(tmp_path)],check=True)
 (tmp_path/'.gitignore').write_text('plugins/*/plugin/public/\n')
 source=tmp_path/'plugins/paint/web/src/main.ts';source.parent.mkdir(parents=True);source.write_text('source v1')
 generated=tmp_path/'plugins/paint/plugin/public/app.js';generated.parent.mkdir(parents=True);generated.write_text('build v1')
 before=code_fingerprint(tmp_path)
 generated.write_text('build v2');assert code_fingerprint(tmp_path)==before
 source.write_text('source v2');assert code_fingerprint(tmp_path)!=before
