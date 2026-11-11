from pathlib import Path
import os,sys,subprocess,time,json,signal
ROOT=Path(__file__).resolve().parents[1];out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13');out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ.get('PATH',''),PLAYWRIGHT_BROWSERS_PATH=str(ROOT/'.tools/playwright'))
with (out/'browser-environment.log').open('w') as log:
 process=subprocess.Popen([sys.executable,'scripts/b13_r1_e2e_env.py'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(1800):
   if (ROOT/'work/b13-r1-session.json').exists():break
   if process.poll() is not None:raise RuntimeError((out/'browser-environment.log').read_text())
   time.sleep(.1)
  assert (ROOT/'work/b13-r1-session.json').exists()
  r=subprocess.run(['npx','playwright','test','--config','playwright.b13-r1.config.ts'],cwd=ROOT,env=env)
 finally:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  code=process.wait(timeout=30)
stats=json.loads((out/'browser.json').read_text())['stats']
ok=r.returncode==0 and code==0 and stats['expected']==5 and stats['unexpected']==stats['skipped']==stats['flaky']==0
(out/'browser-acceptance.json').write_text(json.dumps(dict(status='pass' if ok else 'fail',native_exit=r.returncode,environment_exit=code,counts=stats),indent=2)+'\n')
raise SystemExit(0 if ok else 1)
