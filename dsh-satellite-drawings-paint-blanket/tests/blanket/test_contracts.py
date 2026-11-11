import copy,json
from pathlib import Path
import pytest
from thermal_drawings.domain.validation import validate
from thermal_drawings.domain.errors import ServiceError
from helpers import fixture,opening


@pytest.mark.parametrize('change',['dimensions','opening_id','opening_panel','extra','no_change'])
def test_edit_contract_rejects_unbounded_or_ambiguous_input(change):
    value=dict(result_id='r',baseline_id='b',dimensions_mm=[105,105,105])
    if change=='dimensions':value['dimensions_mm']=[100,float('nan'),100]
    elif change=='opening_id':value['openings']=[opening(),opening()]
    elif change=='opening_panel':value['openings']=[opening('bottom')]
    elif change=='extra':value['baseline_volume_mm3']=100000000
    else:value.pop('dimensions_mm')
    with pytest.raises(ServiceError):validate('blanket',value,'EditShape')


def test_bundle_and_public_contract_copies():
    root=Path(__file__).resolve().parents[2]
    for path in (root/'contracts').glob('*.schema.json'):
        assert path.read_bytes()==(root/'service/src/thermal_drawings/domain/schemas'/path.name).read_bytes()
    api=json.loads((root/'contracts/openapi.yaml').read_text())
    assert '/projects/{id}/blanket-result' in api['paths']


def test_scope_features_not_silently_ignored():
    from thermal_drawings.blanket.pipeline import generate
    p,m=fixture();p['unfold_base_panel']='some-panel'
    with pytest.raises(ValueError,match='unsupported_B11_B13'):generate(p,m,'later-batch')
