import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_batch import verify, assess, test_counts as read_counts

@pytest.fixture
def sandbox(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    tests=tmp_path/'tests';tests.mkdir()
    (tests/'test_real.py').write_text('def test_real():\n    assert sum([2,3]) == 5\n')
    (tmp_path/'evidence.json').write_text('{"status":"pass","value":42}')
    registry={'B01':{'tests':['tests/test_real.py'],'commands':[],'evidence':[{'path':'evidence.json','json_status':'pass'}]}}
    path=tmp_path/'registry.json'
    def run(change=None):
        if change:change(registry)
        path.write_text(json.dumps(registry))
        code=verify('B01',tmp_path/'report',root=tmp_path,registry_path=path)
        return code,json.loads((tmp_path/'report/summary.json').read_text())
    return tmp_path,run

def test_actual_suite_and_hashed_evidence(sandbox):
    root,run=sandbox;code,data=run()
    assert code==0 and data['status']=='passed'
    assert data['tests']=={'required':1,'passed':1,'failed':0,'skipped_required':0}
    assert data['artifacts'][0]['sha256'] and data['commands'][0]['exit_code']==0

def test_build_precommand_runs_before_tests(sandbox):
    root,run=sandbox
    (root/'tests/test_real.py').write_text('from pathlib import Path\ndef test_built():\n    assert Path("built.txt").read_text() == "built"\n')
    code,data=run(lambda r:r['B01'].update(pre_commands=[[sys.executable,'-c','from pathlib import Path; Path("built.txt").write_text("built")']]))
    assert code==0 and data['tests']['passed']==1
    assert data['commands'][0]['argv'][1]=='-c' and data['commands'][1]['argv'][1]=='-m'

def test_failed_precommand_cannot_pass_from_stale_outputs(sandbox):
    _,run=sandbox
    code,data=run(lambda r:r['B01'].update(pre_commands=[[sys.executable,'-c','raise SystemExit(7)']]))
    assert code!=0 and data['status']=='failed' and data['commands'][0]['exit_code']==7

def test_missing_evidence_nonzero(sandbox):
    root,run=sandbox;(root/'evidence.json').unlink()
    code,data=run();assert code!=0 and data['status']=='blocked'

def test_fake_status_evidence_nonzero(sandbox):
    root,run=sandbox;(root/'evidence.json').write_text('{"status":"skip"}')
    code,data=run();assert code!=0 and data['status']=='blocked'

def test_required_skip_nonzero(sandbox):
    root,run=sandbox;(root/'tests/test_real.py').write_text('import pytest\n@pytest.mark.skip(reason="tool missing")\ndef test_real():\n    assert True\n')
    code,data=run();assert code!=0 and data['status']=='blocked' and data['tests']['skipped_required']==1

def test_empty_collection_nonzero(sandbox):
    root,run=sandbox;(root/'tests/test_real.py').write_text('# No tests\n')
    code,data=run();assert code!=0 and data['tests']['required']==0

def test_empty_registry_nonzero(sandbox):
    root,run=sandbox;code,data=run(lambda r:r['B01'].update(tests=[]))
    assert code!=0 and data['status']=='blocked'

def test_unregistered_batch_nonzero(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    p=tmp_path/'registry.json';p.write_text('{}')
    assert verify('B99',tmp_path/'report',root=tmp_path,registry_path=p)!=0
    assert json.loads((tmp_path/'report/summary.json').read_text())['status']=='blocked'

def test_failure_is_not_pass(sandbox):
    root,run=sandbox;(root/'tests/test_real.py').write_text('def test_real():\n    assert False\n')
    code,data=run();assert code!=0 and data['status']=='failed' and data['tests']['failed']==1

def test_required_manual_evidence_nonzero(sandbox):
    _,run=sandbox;code,data=run(lambda r:r['B01'].update(manual_evidence=[{'path':'review.json'}]))
    assert code!=0 and data['status']=='blocked'

def test_stale_generated_evidence_removed(sandbox):
    root,run=sandbox
    code,data=run(lambda r:r['B01'].update(generated_evidence=['evidence.json'],commands=[[sys.executable,'-c','raise SystemExit(1)']]))
    assert code!=0 and not (root/'evidence.json').exists()

def test_missing_registered_test_not_ignored(sandbox):
    _,run=sandbox;code,data=run(lambda r:r['B01']['tests'].append('tests/missing.py'))
    assert code!=0 and data['tests']['required']==0

def test_prerequisite_claim_without_tests_blocked(sandbox):
    root,run=sandbox;(root/'prior.json').write_text(json.dumps({'status':'passed','tests':{'required':0,'skipped_required':0}}))
    code,data=run(lambda r:r['B01'].update(prerequisites=[{'summary':'prior.json'}]))
    assert code!=0 and data['commands']==[]

def test_report_and_registry_paths_cannot_escape(sandbox):
    root,run=sandbox
    with pytest.raises(ValueError):run(lambda r:r['B01'].update(tests=['../outside.py']))

@pytest.mark.parametrize('counts',[{'required':0,'passed':0,'failed':0,'skipped_required':0},{'required':1,'passed':0,'failed':0,'skipped_required':1},{'required':2,'passed':1,'failed':0,'skipped_required':0}])
def test_counts_cannot_fake_pass(counts):assert assess(counts,[],[])!='passed'

def test_junit_requires_each_registered_file(tmp_path):
    p=tmp_path/'junit.xml';p.write_text('<testsuites><testsuite><testcase classname="tests.other" name="test_x"/></testsuite></testsuites>')
    _,missing=read_counts(p,['tests/test_real.py']);assert missing==['tests/test_real.py']
