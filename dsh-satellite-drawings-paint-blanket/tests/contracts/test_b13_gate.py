import copy,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_b13_prerequisites import POLICY,audit
from thermal_drawings.domain.validation import validate
from thermal_drawings.domain.errors import ServiceError
@pytest.mark.parametrize('change',[{'batch':'B14'},{'policy':'ignore-blocked'},{'B12':'docs/evidence/B12/development.json'},{'B09':'docs/evidence/B07/summary.json'}])
def test_development_policy_cannot_be_reused(change):
 with pytest.raises(AssertionError):audit(policy=dict(POLICY,**change))
def test_analysis_requires_bounded_numeric_parameters():
 ref=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text())['model_ref']
 with pytest.raises(ServiceError):validate('complex',dict(face_ref=ref,deflection_mm=float('nan'),cuts_u=[]))
def test_schema_mirrors_are_exact():
 for name in ['blanket','complex','operation','run']:
  assert (ROOT/f'contracts/{name}.schema.json').read_bytes()==(ROOT/f'service/src/thermal_drawings/domain/schemas/{name}.schema.json').read_bytes()

def test_empty_policy_is_not_a_bypass():
 with pytest.raises(AssertionError):audit(policy={})
