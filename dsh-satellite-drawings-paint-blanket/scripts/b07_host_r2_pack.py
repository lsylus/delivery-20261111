"""Build artifacts only under the new worktree; records exact immutable inputs."""
from pathlib import Path
import subprocess, os, json, tarfile, hashlib, argparse
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--npm',required=True);a=p.parse_args()
out=r/'work/host-r2';out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(Path(a.node).parent)+':/usr/bin:/bin',npm_config_cache='/data/qmh/b07-host-r2-runtime/npm-cache')
records=[]
for module in ['paint','blanket']:
 result=subprocess.run([a.node,a.npm,'pack','--json','--pack-destination',str(out)],cwd=r/f'plugins/{module}/plugin',env=env,capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stderr)
 data=json.loads(result.stdout)[0];target=out/'unpacked'/module;target.mkdir(parents=True,exist_ok=True)
 with tarfile.open(out/data['filename']) as f:f.extractall(target,filter='data')
 raw=(out/data['filename']).read_bytes();manifest=json.loads((target/'package/package.json').read_text())
 records.append({'module':module,'filename':data['filename'],'path':str(out/data['filename']),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'name':manifest['name'],'plugin_id':'satellite-'+module,'version':manifest['version'],'engines':manifest['engines'],'files':[x['path'] for x in data['files']]})
(out/'packages.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(records,indent=2))
