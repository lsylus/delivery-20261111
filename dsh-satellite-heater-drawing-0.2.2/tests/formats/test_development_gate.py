"""Keep completed development checks distinct from manufacturing approval."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('development_gate',ROOT/'scripts/check_format_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
E=ROOT/'docs/evidence/B02-development-baseline'

def records():
    return gate.load(E/'human-approval.json'),gate.load(E/'validation/probe-result.json')

def test_pending_manufacturing_approval_allows_verified_development_only():
    approval,probe=records()
    assert approval['status']=='pending'
    assert gate.validate_development(E,approval,probe)==[]
    assert any('pending' in s for s in gate.validate_approval(approval,probe))

@pytest.mark.parametrize('change',['candidate','matrix','fcstd_only','compatibility_claim','missing_gui'])
def test_development_rejects_stale_or_incomplete_real_evidence(monkeypatch,change):
    approval,probe=records();original_load=gate.load
    def modified_load(path):
        value=copy.deepcopy(original_load(path))
        if change=='candidate' and path.name=='B02-development-baseline.json':value['candidate_manifest_sha256']='0'*64
        if change=='matrix' and path.name=='lead-matrix.json':
            key=next(iter(value['artifact_hashes']));value['artifact_hashes'][key]='0'*64
        if change=='fcstd_only' and path.name=='result.json':value['steps']['export_dxf']=False
        if change=='compatibility_claim' and path.name=='summary.json':value['compatibility_status']='passed'
        if change=='missing_gui' and path.name=='gui-attempt.json':value['log']=None
        return value
    monkeypatch.setattr(gate,'load',modified_load)
    assert gate.validate_development(E,approval,probe)

def test_development_rejects_modified_candidate_hash_mapping():
    approval,probe=records();probe=copy.deepcopy(probe)
    key=next(iter(probe['validated_candidate_hashes']));probe['validated_candidate_hashes'][key]='0'*64
    assert any('exact existing candidate' in s for s in gate.validate_development(E,approval,probe))
