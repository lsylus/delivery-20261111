"""Rebuild both locks, prove native imports, clean temporary environment."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'docs/evidence/B01/dependency-rebuild.json'
    temporary=ROOT/'.venv-rebuild-b01'
    if temporary.exists():raise RuntimeError('Temporary rebuild path already exists; do not reuse stale environment')
    result={'status':'fail','commands':[],'resources_created':[str(temporary)],'resources_cleaned':[],'platform':platform.platform(),'python':sys.version,'versions':{}}
    before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('uv.lock','package-lock.json')}
    env=os.environ.copy();env['PATH']=str(ROOT/'.tools/node/bin')+os.pathsep+env.get('PATH','');env['UV_PROJECT_ENVIRONMENT']=str(temporary)
    commands=[['.tools/uv','sync','--frozen','--no-editable','--python',str(Path(sys.base_prefix)/'bin/python3.12')],['.tools/uv','pip','check','--python',str(temporary/'bin/python')],[str(temporary/'bin/python'),'-c','import cadquery,OCP,thermal_drawings,geometry_core,jsonschema,fastapi; print("fresh environment imports OK",cadquery.__version__,OCP.__version__)'],['npm','ci','--ignore-scripts'],['npm','run','typecheck'],['node','-e','import("three").then(m=>{if(m.REVISION!=="184")throw Error("Three revision"); console.log("Three",m.REVISION)})']]
    try:
        for cmd in commands:
            p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
            print(p.stdout,flush=True)
            result['commands'].append({'argv':cmd,'exit_code':p.returncode,'output':p.stdout})
            if p.returncode:raise RuntimeError(f'rebuild command failed: {cmd}')
        for p,h in before.items():
            if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise RuntimeError(f'lock changed during frozen rebuild: {p}')
        result['versions']={n:importlib.metadata.version(n) for n in ('cadquery','cadquery-ocp','jsonschema','pytest','fastapi','uvicorn','PyYAML','openapi-spec-validator')}
        for name,cmd in [('node',['node','--version']),('npm',['npm','--version']),('uv',['.tools/uv','--version'])]:result['versions'][name]=subprocess.check_output(cmd,cwd=ROOT,env=env,text=True).strip()
        result['lock_sha256']=before;result['status']='pass'
    except Exception as e:result['reason']=str(e)
    finally:
        if temporary.exists():
            if temporary.resolve().parent!=ROOT.resolve():raise RuntimeError('unsafe cleanup path')
            shutil.rmtree(temporary);result['resources_cleaned'].append(str(temporary))
        output.write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['status']=='pass' else 2

if __name__=='__main__':raise SystemExit(main())
