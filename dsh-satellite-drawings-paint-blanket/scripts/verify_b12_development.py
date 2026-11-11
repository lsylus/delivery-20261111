"""B12-only development gate, retaining original complete acceptance requirements."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from verify_development import code_fingerprint,assess,digest
from verify_batch import test_counts
ROOT=Path(__file__).resolve().parents[1]
TESTS=['tests/integration/test_blanket_workflow.py','tests/contracts/test_b12_gate.py','tests/blanket/test_net_contracts.py']

def review_check(root,revision,fingerprint):
 try:
  r=json.loads((root/'docs/evidence/B12/independent-review.json').read_text())
  assert r['decision']=='approved' and r['scope']=='B12-development' and r['full_acceptance'] is False and r['reviewer']
  assert r['code_fingerprint']==fingerprint
  if r['code_revision']!=revision:subprocess.run(['git','merge-base','--is-ancestor',r['code_revision'],revision],cwd=root,check=True,capture_output=True)
  assert r['evidence_refs']
  for e in r['evidence_refs']:
   p=(root/e['path']).resolve();assert p.is_relative_to(root.resolve()) and digest(p)==e['sha256']
  return True
 except (OSError,ValueError,KeyError,AssertionError,TypeError,subprocess.CalledProcessError):return False

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',default='docs/evidence/B12');args=parser.parse_args()
 out=(ROOT/args.report_dir).resolve();assert out.is_relative_to(ROOT);out.mkdir(parents=True,exist_ok=True)
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();dirty=bool(subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT));fp=code_fingerprint()
 env=dict(os.environ,B12_EVIDENCE_DIR=str(out.relative_to(ROOT)),PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ['PATH'],TMPDIR=str(ROOT/'work/b12-test-temporary'));Path(env['TMPDIR']).mkdir(parents=True,exist_ok=True)
 xml=out/'development-pytest.xml';xml.unlink(missing_ok=True)
 required=['prerequisites.json','workflow.json','source-provenance.json','browser-acceptance.json','real/exports/summary.json','mcp.json','selection.json','regression/summary.json','source-boundary.json']
 for name in required:(out/name).unlink(missing_ok=True)
 commands=[[sys.executable,'scripts/check_b12_prerequisites.py'],['npm','run','build','--workspaces','--if-present'],['npx','tsc','-p','tsconfig.b07.json'],[sys.executable,'-m','pytest','-q',*TESTS,'--rootdir='+str(ROOT),'--junitxml='+str(xml)],['npm','run','test','--workspace','packages/host-bridge'],[sys.executable,'scripts/check_b12_acceptance.py'],[sys.executable,'scripts/run_b12_browser.py'],[sys.executable,'scripts/check_b12_mcp.py'],['node','scripts/check_b12_selection.mjs'],[sys.executable,'scripts/check_b12_regression.py'],[sys.executable,'scripts/check_source_boundary.py','--output',str(out/'source-boundary.json')]]
 records=[]
 for i,cmd in enumerate(commands,1):
  log=out/f'development-command-{i:02}.log';print('RUN',i,cmd,flush=True)
  try:
   with log.open('w') as f:p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=2400)
   code=p.returncode
  except (OSError,subprocess.TimeoutExpired) as e:log.write_text(str(e));code=124
  records.append(dict(argv=cmd,exit_code=code,log_ref=str(log.relative_to(ROOT)),log_sha256=digest(log)));print('EXIT',i,code,flush=True)
 counts,missing=test_counts(xml,TESTS) if xml.exists() else (dict(required=0,passed=0,failed=0,skipped_required=0),TESTS)
 checks=[dict(id='clean_start',status='pass' if not dirty else 'blocked'),dict(id='source_unchanged',status='pass' if fp==code_fingerprint() else 'fail')]
 for name in required:
  try:ok=json.loads((out/name).read_text())['status']=='pass'
  except (OSError,ValueError,KeyError):ok=False
  checks.append(dict(id=name,status='pass' if ok else 'fail'))
 reviewed=review_check(ROOT,rev,fp);scope=assess(records,counts,checks,missing,True);status=assess(records,counts,checks,missing,reviewed)
 artifacts=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p),bytes=p.stat().st_size) for p in out.rglob('*') if p.is_file() and p.name not in ('development.json','summary.json','independent-review.json','archive-hashes.json')]
 result=dict(schema_version=1,batch_id='B12',scope='B12-development: STEP actual regular equipment, isolated dual views, bounded commands, history, source/BRep-backed bundle restore and true editable DWG drafts',status=status,scope_tests_status=scope,full_acceptance=False,code_revision=rev,dirty=dirty,code_fingerprint=fp,commands=records,tests=counts,missing_test_files=missing,checks=checks,artifacts=artifacts,prerequisites=json.loads((out/'prerequisites.json').read_text()) if (out/'prerequisites.json').exists() else None,independent_review=dict(status='passed' if reviewed else 'pending',record='docs/evidence/B12/independent-review.json',report='docs/reviews/B12.md'),missing_acceptance=[dict(item='B04 AutoCAD open/edit/save/reopen',impact='full DWG acceptance'),dict(item='B05 authorized native ASM/PRT',impact='native input support'),dict(item='B07 formal DSH',impact='formal host deployment'),dict(item='human equipment coverage and manufacturing truth',impact='manufacturing approval; technical selection only')])
 (out/'development.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=status,scope_tests_status=scope,full_acceptance=False)),flush=True)
 return 0 if status=='passed' else 2 if status=='blocked' else 1
if __name__=='__main__':raise SystemExit(main())
