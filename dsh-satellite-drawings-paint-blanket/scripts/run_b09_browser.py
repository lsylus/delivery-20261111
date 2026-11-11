from pathlib import Path
import sys,os,subprocess,time,json,signal
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'docs/evidence/B09';out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ.get('PATH',''),PLAYWRIGHT_BROWSERS_PATH=str(ROOT/'.tools/playwright'))
assert not (ROOT/'work/b09-session.json').exists(),'Existing isolated run must be cleaned first'
with (out/'browser-environment.log').open('w') as log:
 process=subprocess.Popen([sys.executable,'scripts/b09_e2e_env.py'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(1800):
   if (ROOT/'work/b09-session.json').exists():break
   if process.poll() is not None:raise RuntimeError((out/'browser-environment.log').read_text())
   time.sleep(.1)
  assert (ROOT/'work/b09-session.json').exists(),'Environment startup timeout'
  r=subprocess.run(['npx','playwright','test','--config','playwright.b09.config.ts','tests/e2e/paint-workflow.spec.ts'],cwd=ROOT,env=env)
 finally:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  process.wait(timeout=30)
stats=json.loads((out/'browser.json').read_text())['stats']
passed=r.returncode==0 and stats['expected']==8 and stats['unexpected']==stats['skipped']==stats['flaky']==0
(out/'browser-acceptance.json').write_text(json.dumps(dict(status='pass' if passed else 'fail',exit_code=r.returncode,counts=stats),indent=2)+'\n')
raise SystemExit(0 if passed else 1)
