"""Run a bounded host-r2 check and retain native exit code without shell masking."""
import argparse,subprocess,json,os,time
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
assert a.name.replace('-','').replace('_','').isalnum()
out=r/'work/host-r2';out.mkdir(parents=True,exist_ok=True)
log=out/(a.name+'.log');assert not log.exists(), 'Never overwrite a check log'
snapshot=out/(a.name+'-artifacts');snapshot.mkdir()
node='/data/qmh/b07-host-r2-runtime/node-v22.22.2-linux-x64/bin'
env=dict(os.environ,PATH=node+':/usr/bin:/bin',PLAYWRIGHT_BROWSERS_PATH=str(r/'.tools/playwright'))
start=time.time()
with log.open('w') as f:result=subprocess.run(a.command,cwd=r,env=env,stdout=f,stderr=subprocess.STDOUT)
import shutil
for name in ['integration.json','install.json','backend.log','browser-paint.png','browser-blanket.png','browser-host-slots.png','browser-failure.png','browser-failure.txt']:
 src=out/name
 if src.exists() and src.stat().st_mtime>=start:shutil.copy2(src,snapshot/name)
record=dict(command=a.command,exit_code=result.returncode,seconds=round(time.time()-start,2),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True)))
(out/(a.name+'.json')).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));print(log.read_text()[-6000:])
raise SystemExit(result.returncode)
