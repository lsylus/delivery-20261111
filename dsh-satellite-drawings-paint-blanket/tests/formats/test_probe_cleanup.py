"""Probe lifecycle tests do not count simulated subprocesses as CAD acceptance."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import probe_alternative_cad as probe


@pytest.fixture
def sandbox(tmp_path):
    (tmp_path/'work/config').mkdir(parents=True)
    (tmp_path/'work/config/converters.local.json').write_text(json.dumps({'dwg':{'executable':'/test-only'}}))
    evidence=tmp_path/'docs/evidence/B04'
    evidence.mkdir(parents=True)
    (evidence/'sample.dwg').write_bytes(b'negative-test-fixture')
    (evidence/'alternative-cad.json').write_bytes(b'preserve archived failure')
    return tmp_path


@pytest.mark.parametrize('case',['success','nonzero','timeout','spawn_error','bad_config','missing_tool'])
def test_finally_cleans_work_and_preserves_archive(sandbox,monkeypatch,case):
    monkeypatch.setattr(probe.shutil,'which',lambda _: None if case=='missing_tool' else '/test-only')
    process=Mock(pid=123456)
    process.wait.side_effect=[subprocess.TimeoutExpired('test-only',1),-9] if case=='timeout' else None
    process.wait.return_value=17 if case=='nonzero' else 0
    def start(*args,**kwargs):
        work=Path(kwargs['cwd'])
        (work/'temporary-child-file').write_text('must be removed')
        if case=='spawn_error':raise OSError('test process launch failure')
        output=Path(kwargs['env']['B04_CAD_OUTPUT'])
        (output/'freecad-result.json').write_text(json.dumps({'status':'test_only_not_CAD_evidence'}))
        return process
    monkeypatch.setattr(probe.subprocess,'Popen',start)
    monkeypatch.setattr(probe.os,'killpg',lambda *args:None)
    if case=='bad_config':(sandbox/'work/config/converters.local.json').write_text('{invalid')
    result=probe.run_probe(sandbox,timeout_s=1)
    assert result['resources_created']==result['resources_cleaned']
    assert all(not Path(path).exists() for path in result['resources_created'])
    assert not list((sandbox/'work').glob('freecad-b04-*'))
    assert (sandbox/'docs/evidence/B04/alternative-cad.json').read_bytes()==b'preserve archived failure'
    if case not in ('spawn_error','bad_config','missing_tool'):
        assert result['commands'][0]['exit_code']==(-9 if case=='timeout' else 17 if case=='nonzero' else 0)
