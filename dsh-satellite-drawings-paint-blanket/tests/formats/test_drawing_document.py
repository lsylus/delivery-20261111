import copy
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from thermal_drawings.drawing.document import DrawingDocument
import thermal_drawings.drawing.document as module

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sample():
    return json.loads((ROOT / 'fixtures/synthetic/drawing_sample.json').read_text())


def test_packaged_schema_matches_contract():
    assert Path(module.__file__).with_name('drawing.schema.json').read_bytes() == (ROOT / 'contracts/drawing.schema.json').read_bytes()


def test_all_entity_kinds_and_copy_isolation(sample):
    doc = DrawingDocument(sample)
    assert {e['kind'] for e in doc.to_dict()['entities']} == {'line','arc','circle','polyline','hatch','text','dimension','point'}
    sample['entities'].clear()
    exported = doc.to_dict()
    exported['entities'].clear()
    assert len(doc.to_dict()['entities']) == 13


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(units='inch'),
    lambda d: d.update(extra='unknown'),
    lambda d: d.update(entities=[]),
    lambda d: d['layers'].append(copy.deepcopy(d['layers'][0])),
    lambda d: d['entities'].append(copy.deepcopy(d['entities'][0])),
    lambda d: d['entities'][0].update(layer='TEXT') or d.update(layers=d['layers'][:-1]),
    lambda d: d['entities'][3].update(radius_mm=-1),
    lambda d: d['entities'][3].update(radius_mm=float('inf')),
    lambda d: d['entities'][0].update(points=[[0,0],[1,1],[0,1],[1,0]]),
    lambda d: d['entities'][0].update(points=[[0,0],[1,1]]),
    lambda d: d['entities'][6].update(end=[0,50]),
    lambda d: d['entities'][4].update(end_angle_rad=0),
    lambda d: d['frame'].update(z_axis=[0,0,-1]),
    lambda d: d['frame'].update(x_axis=[2,0,0]),
    lambda d: d['entities'][2]['outer_loop'].update(orientation='cw'),
    lambda d: d['entities'][2]['holes'][0].update(points=[[140,20],[140,40],[160,40],[160,20]]),
    lambda d: d['entities'][2]['holes'].append(copy.deepcopy(d['entities'][2]['holes'][0])),
    lambda d: d['entities'][2].update(pattern='UNSUPPORTED'),
    lambda d: d['layers'][0].update(line_type='UNKNOWN'),
    lambda d: d['entities'][10].update(text='two\nlines'),
])
def test_invalid_document_rejected_before_export(sample, mutation):
    mutation(sample)
    with pytest.raises((ValueError, ValidationError)):
        DrawingDocument(sample)
