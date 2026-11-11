import copy,json
from pathlib import Path
import pytest
from thermal_drawings.domain.validation import validate
from thermal_drawings.domain.errors import ServiceError
from net_helpers import net

@pytest.mark.parametrize('definition,value',[
('Unfold',dict(result_id='r',settings=dict(fold_seam_ids=['a','a']))),
('Unfold',dict(result_id='r',settings=dict(layouts=[dict(piece_id='p',translation_mm=[0,0],rotation_rad=float('nan'))]))),
('EditSeams',dict(result_id='r',seams=[dict(id='s',kind='join',overlap_owner_panel='p',width_mm=-15)])),
('EditFixedPoints',dict(result_id='r',command=dict(action='spacing',panel_key='p',start_uv_mm=[0,0],end_uv_mm=[10,10],spacing_mm=0))),
('EditFixedPoints',dict(result_id='r',command=dict(action='add',panel_key='p',uv_mm=[1,1],position3d=[0,0,0]))),
('EditFixedPoints',dict(result_id='r',command=dict(action='delete',id='p',uv_mm=[1,1])))])
def test_invalid_net_requests_rejected(definition,value):
    with pytest.raises(ServiceError):validate('blanket',value,definition)

def test_net_result_and_synchronized_contracts():
    validate('blanket',net(),'NetResult')
    root=Path(__file__).resolve().parents[2]
    for path in (root/'contracts').glob('*.schema.json'):assert path.read_bytes()==(root/'service/src/thermal_drawings/domain/schemas'/path.name).read_bytes()
    api=json.loads((root/'contracts/openapi.yaml').read_text());assert '/projects/{id}/blanket-net' in api['paths']
