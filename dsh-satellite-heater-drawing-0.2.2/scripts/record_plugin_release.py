"""Record development verification only after the exact packaged smoke passes."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import tarfile

root = Path(__file__).resolve().parents[1]
release = root / 'dist/plugin-release-20261110'
archive = release / 'qmh-dsh-satellite-heater-drawing-0.2.0.tgz'
smoke_dir = root / 'dist/plugin-smoke-20261110-c'
smoke = json.loads((smoke_dir / 'summary.json').read_text())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
assert smoke['status'] == 'passed' and smoke['archive_sha256'] == digest
evidence = root / 'docs/evidence/plugin-release-20261110'
evidence.mkdir(parents=True, exist_ok=True)

with tarfile.open(archive) as bundle:
    files = {m.name: m for m in bundle.getmembers() if m.isfile()}
    assert not any(re.search(r'(^|/)(node_modules|fixtures|\.venv|jobs-data|\.git)(/|$)|\.(xlsx|shx|bak|sqlite3)$', name, re.I) for name in files)
    package = json.load(bundle.extractfile('package/package.json'))
    for name in ['src/index.mjs', 'lib/client.js', 'public/pdf.mjs', 'public/pdf.worker.mjs', 'runtime/bootstrap.py', 'cordis.patch.yml']:
        assert 'package/' + name in files
    runtime = json.load(bundle.extractfile('package/runtime/files.json'))
    for name, expected in runtime.items():
        assert hashlib.sha256(bundle.extractfile('package/runtime/' + name).read()).hexdigest() == expected
    inventory = [{'path': name, 'bytes': member.size,
                  'sha256': hashlib.sha256(bundle.extractfile(member).read()).hexdigest()}
                 for name, member in sorted(files.items())]

logs = {
    'regression.log': '/tmp/heater-plugin-regression-final.log',
    'native-decisions.log': '/tmp/heater-engine-decisions.log',
    'host.log': '/tmp/heater-plugin-host-final.log',
    'client.log': '/tmp/heater-packaged-client.log',
    'packaged-smoke.log': '/tmp/heater-packaged-smoke-c.log',
}
for filename, source in logs.items():
    shutil.copyfile(source, evidence / filename)
assert '176 passed' in (evidence / 'regression.log').read_text()
assert '2 passed' in (evidence / 'native-decisions.log').read_text()
assert '# pass 5' in (evidence / 'host.log').read_text()
assert 'PASS:' in (evidence / 'client.log').read_text()
for name in ['summary.json', 'ready.png', 'generated-preview.png', 'narrow.png']:
    shutil.copyfile(smoke_dir / name, evidence / ('smoke-' + name))
(evidence / 'package-files.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
summary = {
    'status': 'passed', 'scope': 'development verification of the exact npm tgz on 5090',
    'package': package['name'], 'version': package['version'],
    'archive': str(archive), 'sha256': digest, 'bytes': archive.stat().st_size,
    'file_count': len(files), 'runtime_hash_checks': len(runtime),
    'python_regression_passed': 176, 'native_decision_tests_passed': 2,
    'host_tests_passed': 5, 'packaged_client_registration': 'passed',
    'packaged_end_to_end_checks_passed': len(smoke['checks']),
    'backend': 'real bundled offline environment', 'cad': 'real OpenCADStudio native DWG save/reopen/print',
    'host_adapter': 'mocked authenticated DSH services', 'browser': 'real Chromium/Playwright',
    'real_dsh_installation': 'not_run_user_accepted', 'autocad_reopen': 'not_run',
    'formal_engineering_approval': 'not_run',
    'policies': ['Excel business fields authoritative', 'engineer sample printing retained',
                 'controlled template structure', 'generated output pending engineering review'],
}
(evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
(release / 'SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n')
shutil.copyfile(evidence / 'summary.json', release / 'acceptance-summary.json')
print(json.dumps(summary, ensure_ascii=False))
