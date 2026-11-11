"""B13 scoped implementation verification. Original full gate remains strict."""
import argparse,os,json,subprocess,sys
from pathlib import Path
from verify_development import code_fingerprint,digest,assess
from verify_batch import test_counts
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['tests/blanket/test_complex_envelope.py','tests/blanket/test_developable.py','tests/blanket/test_piecewise_mapping.py','tests/paint/test_complex_targets.py','tests/integration/test_revision_rebinding.py']
EXTRA=['tests/integration/test_b13_workflow.py','tests/contracts/test_b13_gate.py']
def review_check(revision,fp):
 try:
  r=json.loads((ROOT/'docs/evidence/B13/independent-review.json').read_text())
  assert r['scope']=='B13-development' and r['decision']=='approved' and r['full_acceptance'] is False and r['reviewer']
  assert r['code_fingerprint']==fp
  subprocess.run(['git','merge-base','--is-ancestor',r['code_revision'],revision],cwd=ROOT,check=True,capture_output=True)
  for e in r['evidence_refs']:
   p=(ROOT/e['path']).resolve();assert p.is_relative_to(ROOT) and digest(p)==e['sha256']
  return True
 except (OSError,KeyError,ValueError,AssertionError,subprocess.CalledProcessError):return False
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',default='docs/evidence/B13');args=parser.parse_args()
 out=(ROOT/args.report_dir).resolve();assert out.is_relative_to(ROOT)
 out.mkdir(parents=True,exist_ok=True)
 # Do not overwrite previous attempts. The final root may contain survey/history,
 # but a completed development record always requires a new report directory.
 assert not (out/'development.json').exists(),'Use a new report directory; preserve previous receipts'
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 dirty=bool(subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT))
 fp=code_fingerprint();temp=ROOT/'work/b13-test-temporary';temp.mkdir(exist_ok=True)
 env=dict(os.environ,B13_EVIDENCE_DIR=str(out.relative_to(ROOT)),TMPDIR=str(temp),PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ['PATH'])
 cmds=[[sys.executable,'scripts/check_b13_prerequisites.py'],['npm','run','build','--workspaces','--if-present'],['npx','tsc','-p','tsconfig.b07.json'],
       [sys.executable,'-m','pytest','-q',*REQUIRED,'--rootdir='+str(ROOT),'--junitxml='+str(out/'required.xml')],
       [sys.executable,'-m','pytest','-q',*EXTRA,'--rootdir='+str(ROOT),'--junitxml='+str(out/'extra.xml')],
       ['npm','run','test','--workspace','packages/host-bridge'],[sys.executable,'scripts/check_b13_measurements.py'],
       [sys.executable,'scripts/run_b13_browser.py'],[sys.executable,'scripts/check_b13_regression.py'],
       [sys.executable,'scripts/check_source_boundary.py','--output',str(out/'source-boundary.json')]]
 records=[]
 for i,cmd in enumerate(cmds,1):
  path=out/f'command-{i:02}.log';print('RUN',i,cmd,flush=True)
  try:
   with path.open('w') as log:p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
   code=p.returncode
  except (OSError,subprocess.TimeoutExpired) as error:
   with path.open('a') as log:log.write(str(error))
   code=124
  records.append(dict(argv=cmd,exit_code=code,log_ref=str(path.relative_to(ROOT)),log_sha256=digest(path)))
  print('EXIT',i,code,flush=True)
 counts=dict(required=0,passed=0,failed=0,skipped_required=0);missing=[]
 for name,tests in [('required',REQUIRED),('extra',EXTRA)]:
  if not (out/(name+'.xml')).exists():missing+=tests;continue
  c,m=test_counts(out/(name+'.xml'),tests);missing+=m
  for k,v in c.items():counts[k]+=v
 checks=[dict(id='clean_start',status='pass' if not dirty else 'blocked'),dict(id='source_unchanged',status='pass' if fp==code_fingerprint() else 'fail')]
 for name in ['prerequisites.json','measurements/acceptance.json','http/workflow.json','browser-acceptance.json','browser-resources.json','regression/summary.json','source-boundary.json']:
  try:ok=json.loads((out/name).read_text())['status']=='pass'
  except (OSError,ValueError,KeyError):ok=False
  checks.append(dict(id=name,status='pass' if ok else 'fail'))
 reviewed=review_check(rev,fp);scope=assess(records,counts,checks,missing,True)
 # Measurements and tests cannot self-approve absent manufacturing standards.
 acceptance=json.loads((out/'measurements/acceptance.json').read_text()) if (out/'measurements/acceptance.json').exists() else {}
 blockers=acceptance.get('blockers',[dict(id='missing_required_measurements')])
 status='failed' if scope=='failed' else 'blocked' if blockers or not reviewed or scope!='passed' else 'passed'
 artifacts=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p),bytes=p.stat().st_size) for p in out.rglob('*') if p.is_file() and p.name not in ['development.json','summary.json','archive-hashes.json']]
 result=dict(schema_version=1,batch_id='B13',scope='B13 technical implementation and native measurements; required manufacturing scenarios remain explicitly blocked',status=status,
             scope_tests_status=scope,full_acceptance=False,code_revision=rev,dirty=dirty,code_fingerprint=fp,commands=records,tests=counts,
             missing_test_files=missing,checks=checks,artifacts=artifacts,prerequisites=json.loads((out/'prerequisites.json').read_text()) if (out/'prerequisites.json').exists() else None,
             independent_review=dict(status='passed' if reviewed else 'pending',record='docs/evidence/B13/independent-review.json'),
             blocked_required_scenarios=blockers,retained_full_blockers=['B04 AutoCAD','B05 authorized native','B07 formal DSH','B09/B12 full blocked'])
 (out/'development.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(status=status,scope_tests_status=scope,tests=counts,full_acceptance=False)),flush=True)
 return 1 if status=='failed' else 2 if status=='blocked' else 0
if __name__=='__main__':raise SystemExit(main())
