"""Install the locked geometry package non-editably in a clean disposable venv."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/B02'
def main():
    result={'status':'failed','commands':[],'resources_created':[],'resources_cleaned':[]}
    def run(argv,env=None,cwd=ROOT):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        result['commands'].append({'argv':list(map(str,argv)),'exit_code':p.returncode,'output':p.stdout})
        if p.returncode:raise RuntimeError(p.stdout)
    try:
        with tempfile.TemporaryDirectory(prefix='b02-isolated-',dir=ROOT/'work') as temp:
            folder=Path(temp);venv=folder/'venv';result['resources_created'].append(str(folder))
            env={**os.environ,'UV_PROJECT_ENVIRONMENT':str(venv)};env.pop('PYTHONPATH',None)
            run([ROOT/'.tools/uv','sync','--frozen','--no-editable','--package','satellite-geometry-core','--reinstall-package','satellite-geometry-core','--python',sys.executable],env)
            code="""import sys,json
from pathlib import Path
import geometry_core
from geometry_core.serialization import read_step_summary
p=Path(geometry_core.__file__).resolve()
assert 'site-packages' in str(p) and 'geometry-core/src' not in str(p)
assert not any(k=='backend' or k.startswith('backend.') for k in sys.modules)
source=Path(sys.argv[1])
facts=read_step_summary(source)
assert facts.topology.solid_count==3 and facts.topology.face_count==19
s=geometry_core.load_model_snapshot(source,project_id='isolated',model_id='assembly',model_revision=1,asset_id='asset',output_dir=Path(sys.argv[2]))
assert len(s['instances'])==5
print(json.dumps({'package':str(p),'instances':len(s['instances']),'volume_mm3':facts.volume_mm3,'legacy_imports':False}))
"""
            run([venv/'bin/python','-I','-c',code,ROOT/'fixtures/synthetic/assembly-tree.step',folder/'snapshot'],env,folder)
            run([ROOT/'.tools/uv','pip','check','--python',venv/'bin/python'],env)
            result['status']='pass'
        result['resources_cleaned'].append(str(folder))
    except Exception as exc:result['error']=str(exc)
    finally:
        for resource in result['resources_created']:
            if not Path(resource).exists() and resource not in result['resources_cleaned']:
                result['resources_cleaned'].append(resource)
        (OUT/'isolated-environment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='pass' else 2
if __name__=='__main__':raise SystemExit(main())
