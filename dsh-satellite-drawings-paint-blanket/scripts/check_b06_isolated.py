"""Fresh non-editable service + geometry install; HTTP workflow from site-packages."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evidence/B06'


def main():
    result = dict(status='failed', commands=[], resources_created=[], resources_cleaned=[])
    def run(argv, env, cwd=ROOT):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        result['commands'].append(dict(argv=list(map(str, argv)), exit_code=p.returncode, output=p.stdout))
        if p.returncode:
            raise RuntimeError(p.stdout)
    try:
        with tempfile.TemporaryDirectory(prefix='b06-isolated-', dir=ROOT / 'work') as temp:
            folder = Path(temp); venv = folder / 'venv'
            result['resources_created'].append(str(folder))
            env = {**os.environ, 'UV_PROJECT_ENVIRONMENT': str(venv)}
            env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
            run([ROOT / '.tools/uv', 'sync', '--frozen', '--no-editable', '--package', 'thermal-drawings-service',
                 '--reinstall-package', 'thermal-drawings-service', '--reinstall-package', 'satellite-geometry-core', '--python', sys.executable], env)
            code = '''import sys,json,importlib.util
from pathlib import Path
import thermal_drawings, geometry_core
assert 'site-packages' in str(Path(thermal_drawings.__file__).resolve())
assert 'site-packages' in str(Path(geometry_core.__file__).resolve())
assert not any(k=='backend' or k.startswith('backend.') for k in sys.modules)
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('harness',root/'tests/runtime/http_harness.py')
harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
s=harness.Service(Path(sys.argv[2])/'http')
try:
 p,a,r,job=s.imported()
 saved=s.wait(s.operation(p,r)['run_id'])
 assert saved['state']=='succeeded'
 changed=s.edit(p,r,{'value':5})
 restored=s.wait(s.operation(p,changed,'engineering.restore',{'artifact_id':saved['artifacts'][0]['id']})['run_id'])
 assert restored['state']=='succeeded'
 s.stop();s.start()
 assert s.call('GET','/runs/'+job['id'])[1]['state']=='succeeded'
 print(json.dumps({'service':thermal_drawings.__file__,'geometry':geometry_core.__file__,'artifacts':len(job['artifacts']),'save_restore_restart':'pass','legacy_imports':False}))
finally:s.close()
'''
            run([venv / 'bin/python', '-I', '-c', code, ROOT, folder], env, folder)
            run([ROOT / '.tools/uv', 'pip', 'check', '--python', venv / 'bin/python'], env)
            result['status'] = 'pass'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        for path in result['resources_created']:
            if not Path(path).exists():
                result['resources_cleaned'].append(path)
        (OUT / 'isolated-environment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
