"""Negative branch tests only. Fake processes never establish successful DWG capability."""
import json
import os
from pathlib import Path
import sys
import time

import pytest

from thermal_drawings.drawing.converter import DwgConverter, ConversionError
from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.dxf_export import DrawingExporter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from check_b04_acceptance import assess_evidence
from verify_batch import prerequisite_artifact_matches, assess


def test_missing_tool_and_license_are_blocked(tmp_path):
    converter = DwgConverter({'adapter':'oda_file_converter','executable':str(tmp_path/'not-installed'),'license_ref':None})
    caps = converter.capabilities()
    assert caps['status'] == 'blocked'
    assert 'converter_executable_missing' in caps['reasons']
    with pytest.raises(ConversionError, match='converter_executable_missing'):
        converter.convert(tmp_path/'x.dxf',tmp_path/'x.dwg',document=None)
    assert not (tmp_path/'x.dwg').exists()


def test_installed_executable_without_license_is_not_ready():
    caps = DwgConverter({'adapter':'oda_file_converter','executable':sys.executable,'license_ref':None}).capabilities()
    assert caps['status'] == 'blocked' and caps['license_state'] == 'unverified'


def test_nonzero_command_recorded():
    converter = DwgConverter({})
    with pytest.raises(ConversionError) as exc:
        converter._run([sys.executable,'-c','raise SystemExit(17)'],3,ROOT)
    assert exc.value.code == 'converter_failed'
    assert converter.commands[0]['exit_code'] == 17


def test_timeout_kills_entire_process_group(tmp_path):
    child = tmp_path/'child.pid'
    script = "import subprocess,time,pathlib,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    converter = DwgConverter({})
    with pytest.raises(ConversionError) as exc:
        converter._run([sys.executable,'-c',script,str(child)],1,tmp_path)
    assert exc.value.code == 'converter_timeout'
    pid = int(child.read_text())
    status = Path(f'/proc/{pid}/stat')
    # SIGKILL delivery and orphan reaping are asynchronous. X/x are Linux dead
    # states; Z is a non-running zombie. Never accept a live sleeping child.
    deadline = time.monotonic()+1
    while True:
        try:
            state = status.read_text().split()[2]
        except (FileNotFoundError, ProcessLookupError):
            state = 'gone'
        if state in ('X', 'x', 'Z', 'gone') or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert state in ('X', 'x', 'Z', 'gone')


@pytest.mark.parametrize('output_kind', ['missing','dxf_renamed','header_only'])
def test_fake_converter_cannot_publish(tmp_path, monkeypatch, output_kind):
    document = DrawingDocument.read(ROOT/'fixtures/synthetic/drawing_sample.json')
    dxf = DrawingExporter().write_dxf(document,tmp_path/'input.dxf')
    font = tmp_path/'DroidSansFallbackFull.ttf'; font.write_bytes(b'negative-test-only')
    converter = DwgConverter({'target_version':'ACAD2018','timeout_s':1,'font_paths':[str(font)]})
    monkeypatch.setattr(converter,'capabilities',lambda: {'status':'ready_unverified','headless_runner':'fake-xvfb','executable':'fake-converter'})
    def fake(argv, timeout, cwd):
        if output_kind == 'missing': return
        output = Path(argv[4])
        if argv[6] == 'DWG':
            (output/'sample.dwg').write_bytes(dxf.read_bytes() if output_kind == 'dxf_renamed' else b'AC1032not-a-real-dwg')
        # Deliberately no reverse output: a header is not proof of DWG.
    monkeypatch.setattr(converter,'_run',fake)
    with pytest.raises(ConversionError): converter.convert(dxf,tmp_path/'result.dwg',document=document)
    assert not (tmp_path/'result.dwg').exists()
    assert not list(tmp_path.glob('.dwg-*'))


def test_no_conversion_or_autocad_evidence_is_blocked(tmp_path):
    assert assess_evidence(tmp_path)['status'] == 'blocked'


def test_explicit_external_block_exit_is_not_pass_or_failure():
    counts = {'required':1,'passed':1,'failed':0,'skipped_required':0}
    assert assess(counts,[{'exit_code':3}],[],blocked_exit_codes=[3]) == 'blocked'
    assert assess(counts,[{'exit_code':1}],[],blocked_exit_codes=[3]) == 'failed'


def test_prerequisite_source_uses_accepted_commit(tmp_path):
    import subprocess, hashlib
    def git(*args): return subprocess.check_output(['git',*args],cwd=tmp_path).decode().strip()
    git('init','-q'); git('config','user.name','B04 test'); git('config','user.email','test@example.invalid')
    (tmp_path/'source.py').write_bytes(b'accepted')
    git('add','source.py'); git('commit','-qm','accepted')
    revision = git('rev-parse','HEAD')
    (tmp_path/'source.py').write_bytes(b'later batch changes')
    record = {'path':'source.py','sha256':hashlib.sha256(b'accepted').hexdigest()}
    assert prerequisite_artifact_matches(tmp_path, revision, record)
    assert not prerequisite_artifact_matches(tmp_path, revision, {**record,'sha256':'0'*64})
    evidence=tmp_path/'docs/evidence/B01'; evidence.mkdir(parents=True)
    report=evidence/'runtime.json'; report.write_bytes(b'final runtime evidence')
    runtime={'path':'docs/evidence/B01/runtime.json','sha256':hashlib.sha256(report.read_bytes()).hexdigest()}
    assert prerequisite_artifact_matches(tmp_path,revision,runtime)
    report.write_bytes(b'tampered runtime evidence')
    assert not prerequisite_artifact_matches(tmp_path,revision,runtime)
