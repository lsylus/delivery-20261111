import json
import math
from pathlib import Path

import ezdxf
import pytest

from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.dxf_export import DrawingExporter
from thermal_drawings.drawing.validation import validate_dxf

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def exported(tmp_path):
    document = DrawingDocument.read(ROOT / 'fixtures/synthetic/drawing_sample.json')
    path = DrawingExporter().write_dxf(document, tmp_path / 'sample.dxf')
    return document, path


def test_actual_file_entities_units_dimensions_holes_chinese(exported):
    document, path = exported
    result = validate_dxf(document, path)
    assert result['entity_counts'] == {'LWPOLYLINE':4,'HATCH':1,'CIRCLE':1,'ARC':2,'LINE':1,'POINT':1,'TEXT':1,'DIMENSION':2}
    doc = ezdxf.readfile(path)
    assert doc.units == 4
    dims = list(doc.modelspace().query('DIMENSION'))
    assert [d.get_measurement() for d in dims] == pytest.approx([100,60])
    hatch = doc.modelspace().query('HATCH')[0]
    assert len(hatch.paths) == 2 and hatch.dxf.hatch_style == 0
    assert bool(hatch.paths[0].path_type_flags & 1)
    assert not bool(hatch.paths[1].path_type_flags & 1)
    outer_area = 100*60
    hole_area = 20*20
    assert outer_area-hole_area == 5600
    assert '喷漆保护区' in doc.modelspace().query('TEXT')[0].dxf.text
    arcs = list(doc.modelspace().query('ARC'))
    assert (arcs[0].dxf.start_angle,arcs[0].dxf.end_angle) == pytest.approx((0,90))
    assert (arcs[1].dxf.start_angle,arcs[1].dxf.end_angle) == pytest.approx((90,0))


@pytest.mark.parametrize('corruption', ['scale','hole','chinese','dimension','layer','units','duplicate','linetype'])
def test_readback_detects_real_file_corruption(exported, corruption):
    document, path = exported
    doc = ezdxf.readfile(path)
    space = doc.modelspace()
    if corruption == 'scale': space.query('CIRCLE')[0].dxf.radius *= 25.4
    if corruption == 'hole': space.query('HATCH')[0].paths.paths.pop()
    if corruption == 'chinese': space.query('TEXT')[0].dxf.text = '???'
    if corruption == 'dimension': space.query('DIMENSION')[0].dxf.defpoint3 = (99,0,0)
    if corruption == 'layer': space.query('LINE')[0].dxf.layer = '0'
    if corruption == 'units': doc.units = 1
    if corruption == 'duplicate': space.add_point((0,0))
    if corruption == 'linetype': doc.layers.get('FOLD').dxf.linetype = 'CONTINUOUS'
    doc.saveas(path)
    with pytest.raises((ValueError, KeyError)):
        validate_dxf(document, path)


def test_existing_dxf_survives_write_validation_failure(exported, monkeypatch):
    document, path = exported
    before = path.read_bytes()
    def reject(*args): raise ValueError('deliberate prepublication failure')
    monkeypatch.setattr('thermal_drawings.drawing.validation.validate_dxf', reject)
    with pytest.raises(ValueError): DrawingExporter().write_dxf(document, path)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_diagonal_aligned_dimension(tmp_path):
    data = json.loads((ROOT / 'fixtures/synthetic/drawing_sample.json').read_text())
    data['entities'] = [dict(id='diagonal',kind='dimension',layer='DIMENSION',source_refs=[],start=[0,0],end=[3,4],position=[-4,3],text_override=None)]
    doc = DrawingDocument(data)
    path = DrawingExporter().write_dxf(doc, tmp_path/'diagonal.dxf')
    assert ezdxf.readfile(path).modelspace().query('DIMENSION')[0].get_measurement() == pytest.approx(5)
