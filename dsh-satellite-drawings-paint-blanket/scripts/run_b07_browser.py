from pathlib import Path
import sys,subprocess,time,json,os,signal,shutil
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/evidence/B07';out.mkdir(parents=True,exist_ok=True)
specs=sys.argv[1:] or ['tests/e2e/workspace-isolation.spec.ts','tests/e2e/model-selection.spec.ts','tests/e2e/live-failure.spec.ts']
assert all(s in ['tests/e2e/workspace-isolation.spec.ts','tests/e2e/model-selection.spec.ts','tests/e2e/live-failure.spec.ts'] for s in specs)
env=os.environ.copy();env['PATH']=str(ROOT/'.tools/node/bin')+os.pathsep+env.get('PATH','');env['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.tools/playwright')
records=[];resources=[];all_ok=True
for spec in specs:
 name=Path(spec).name.removesuffix('.spec.ts');log=(out/(name+'-environment.log')).open('w')
 process=subprocess.Popen([sys.executable,'scripts/b07_e2e_env.py'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(1200):
   if (ROOT/'work/b07-session.json').exists():break
   if process.poll() is not None:raise RuntimeError('Environment failed: '+(out/(name+'-environment.log')).read_text())
   time.sleep(.1)
  assert (ROOT/'work/b07-session.json').exists(),'Environment startup timeout'
  print('RUNNING',spec,flush=True)
  result=subprocess.run(['npx','playwright','test',spec],cwd=ROOT,env=env)
  all_ok=all_ok and result.returncode==0
  records.append(dict(spec=spec,exit_code=result.returncode))
 finally:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  process.wait(timeout=30);log.close()
  artifact_dir=out/'artifacts'
  if artifact_dir.exists():shutil.copytree(artifact_dir,out/(name+'-artifacts'),dirs_exist_ok=True)
  for f in ['browser.json','api.jsonl','live-inputs.json','resources.json','mcp.json']:
   p=out/f
   if p.exists():shutil.copyfile(p,out/(name+'-'+f))
  if (out/'resources.json').exists():resources.append(json.loads((out/'resources.json').read_text()))
counts=dict(passed=0,failed=0,skipped=0)
for record in records:
 p=out/(Path(record['spec']).name.removesuffix('.spec.ts')+'-browser.json')
 if p.exists():
  stats=json.loads(p.read_text())['stats'];counts['passed']+=stats['expected'];counts['failed']+=stats['unexpected'];counts['skipped']+=stats['skipped']
result=dict(status='pass' if all_ok and counts['passed']>0 and counts['failed']==counts['skipped']==0 else 'fail',commands=records,counts=counts,
 resources_created=[v for r in resources for v in r['resources_created']],resources_cleaned=[v for r in resources for v in r['resources_cleaned']])
(out/'browser-acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
raise SystemExit(0 if result['status']=='pass' else 1)
