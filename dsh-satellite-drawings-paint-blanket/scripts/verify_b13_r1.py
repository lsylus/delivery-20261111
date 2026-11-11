"""R1 executable evidence gate. Technical pass never grants review approval."""
import os,sys,json,subprocess,argparse
from pathlib import Path
from verify_development import code_fingerprint,digest
from verify_batch import test_counts
from verify_b13_development import REQUIRED,EXTRA
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',required=True);args=parser.parse_args();out=(ROOT/args.report_dir).resolve();assert out.is_relative_to(ROOT) and not out.exists();out.mkdir(parents=True)
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();dirty=bool(subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT));fp=code_fingerprint()
 assert not dirty,'Commit implementation and probe evidence before running this gate'
 focused=REQUIRED+['tests/blanket/test_native_surface_manufacturing.py','tests/paint/test_native_surface_result.py']
 env=dict(os.environ,B13_EVIDENCE_DIR=str(out.relative_to(ROOT)),PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ['PATH'])
 commands=[[sys.executable,'scripts/check_b13_prerequisites.py'],['npm','run','build'],['npm','run','typecheck'],[sys.executable,'-m','pytest','-q',*focused,'--junitxml='+str(out/'required.xml')],[sys.executable,'-m','pytest','-q',*EXTRA,'--junitxml='+str(out/'extra.xml')],['npm','run','test','--workspace','packages/host-bridge'],[sys.executable,'scripts/check_b13_measurements.py'],[sys.executable,'scripts/b13_r1_workflow.py'],[sys.executable,'scripts/b13_r1_paint_workflow.py'],[sys.executable,'scripts/run_b13_r1_browser.py'],[sys.executable,'scripts/check_b13_regression.py'],[sys.executable,'scripts/check_source_boundary.py','--output',str(out/'source-boundary.json')]]
 records=[]
 for i,cmd in enumerate(commands,1):
  log=out/f'command-{i:02}.log';print('RUN',i,flush=True)
  try:
   with log.open('w') as f:proc=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=2400)
   code=proc.returncode
  except (OSError,subprocess.TimeoutExpired) as error:
   with log.open('a') as f:f.write(str(error))
   code=124
  records.append(dict(argv=cmd,exit_code=code,log_ref=str(log.relative_to(ROOT)),log_sha256=digest(log)));print('EXIT',i,code,flush=True)
  if code:break  # Missing later checks remain failures; never consume partial success.
 counts={};missing=[]
 for name,files in [('required',focused),('extra',EXTRA)]:
  if (out/(name+'.xml')).exists():counts[name],absent=test_counts(out/(name+'.xml'),files);missing+=absent
  else:missing+=files
 check_files=['prerequisites.json','measurements/acceptance.json','http/workflow.json','r1-http/workflow.json','r1-paint-http/workflow.json','browser-acceptance.json','browser-resources.json','regression/summary.json','source-boundary.json'];checks=[]
 for name in check_files:
  try:ok=json.loads((out/name).read_text())['status']=='pass'
  except (OSError,ValueError,KeyError):ok=False
  checks.append(dict(id=name,status='pass' if ok else 'fail'))
 unchanged=fp==code_fingerprint() and not subprocess.check_output(['git','diff',rev,'--','service','packages','plugins','contracts','scripts','tests','fixtures','*.json','*.ts'],cwd=ROOT);ok=unchanged and not missing and all(c['exit_code']==0 for c in records) and all(c['status']=='pass' for c in checks) and all(c['required']==c['passed']>0 and c['failed']==c['skipped_required']==0 for c in counts.values())
 value=dict(schema_version=1,batch_id='B13',round='R1',status='blocked' if ok else 'failed',scope_tests_status='passed' if ok else 'failed',full_acceptance=False,code_revision=rev,code_fingerprint=fp,dirty=False,source_unchanged=unchanged,commands=records,tests=counts,missing_test_files=missing,checks=checks,independent_review=dict(status='pending',original_decision='FAIL',original_report='docs/reviews/B13.md'),limitations=['Native fitted surfaces have zero clearance; selected-surface scope is not complete equipment coverage','Sphere body chart remains approximate; supported meridional tabs compensate to requested physical geodesic width with native-circle readback; material strain remains unapproved','Curved bosses and multi-occurrence curved contact require native footprints/process decisions','Full motor and fuel-tank STEP import retain degenerate triangle failures; HTTP/browser use explicitly documented source-derived scopes','Original B04/B05/B07/B09/B12 full blockers retained'])
 (out/'development.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({k:value[k] for k in ['status','scope_tests_status','tests','code_revision']}),flush=True);return 2 if ok else 1
if __name__=='__main__':raise SystemExit(main())
