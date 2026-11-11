"""Build the independent packaged runtime without bundling inputs or private data."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / 'plugin/runtime'
for name, source in [('service', ROOT/'service'), ('templates', ROOT/'templates'), ('schemas', ROOT/'schemas')]:
    target = runtime/name
    if target.exists():
        assert target.parent == runtime
        shutil.rmtree(target)
    if name == 'service':
        shutil.copytree(source/'src', target/'src', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    else:
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
requirements = ROOT/'dist/heater-runtime-requirements.txt'
assert requirements.is_file()
shutil.copyfile(requirements, runtime/'requirements.txt')
target = runtime/'wheels'
if target.exists():
    assert target.parent == runtime
    shutil.rmtree(target)
shutil.copytree(ROOT/'dist/heater-wheelhouse',target)
files = {}
for file in sorted(runtime.rglob('*')):
    if file.is_file() and file.name != 'files.json':
        files[file.relative_to(runtime).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
(runtime/'files.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n')
print(json.dumps({'files':len(files),'bytes':sum(p.stat().st_size for p in runtime.rglob('*') if p.is_file())}))
