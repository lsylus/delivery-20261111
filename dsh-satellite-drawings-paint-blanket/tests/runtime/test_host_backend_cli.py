import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_init_writes_validated_production_worker_and_converter_settings(tmp_path):
    converter = tmp_path / 'converter.json'
    converter.write_text('{}')
    backend = tmp_path / 'backend'
    completed = subprocess.run([
        sys.executable,
        str(ROOT / 'scripts/host_backend.py'),
        '--allowed-parent', str(tmp_path),
        '--root', str(backend),
        'init',
        '--converter-config', str(converter),
    ], check=True, text=True, stdout=subprocess.PIPE)
    result = json.loads(completed.stdout)
    config = json.loads((backend / 'config.json').read_text())
    assert result['configured'] is True
    assert config['timeout_s'] == 900
    assert config['memory_limit_mb'] == 32768
    assert config['concurrency'] == 1
    assert config['converter_config'] == str(converter.resolve())
    assert (backend.stat().st_mode & 0o077) == 0
    assert ((backend / 'data').stat().st_mode & 0o077) == 0
    assert ((backend / 'hosts.json').stat().st_mode & 0o077) == 0
