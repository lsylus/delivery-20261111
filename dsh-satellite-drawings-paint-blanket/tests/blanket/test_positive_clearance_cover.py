import copy
import json
import math
import cadquery as cq
import pytest
from shapely.geometry import shape as polygon_shape
from helpers import ROOT, fixture, check
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.faceted_cover import construct
from thermal_drawings.blanket.exterior import close_recesses
from thermal_drawings.blanket.selection import shape_hash


def motor():
    source=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
    box=source.BoundingBox()
    source=source.translate((-box.xmin,-box.ymin,-box.zmin))
    p,m=fixture(shape=source)
    p.update(envelope_policy='faceted_clearance_v1',clearance_options=dict(clearance_mm=1.,section_cuts_mm=[40.,300.,334.]))
    p['allowance']['factors']=[1,1,1]
    return source,p,m


def test_full_real_motor_native_cover_connected_material_and_fixed_baseline(tmp_path):
    source,p,m=motor();cover=generate(p,m,'r3-real',tmp_path)
    assert len(source.Faces())==44 and len(cover['panels'])>5
    assert cover['status']=='needs_review'
    baseline=cq.Shape.importBrep(str(tmp_path/'baseline.brep'))
    solid=cq.Shape.importBrep(str(tmp_path/'evaluation.brep'))
    material=cq.Shape.importBrep(str(tmp_path/'manufacturing.brep'))
    assert baseline.Volume()==pytest.approx(5637234.35462044,rel=1e-8)
    assert 1<solid.Volume()/baseline.Volume()<1.2
    source_hash=shape_hash(source)
    # CadQuery's convenience Cut may update retained OCCT tolerances/pcurves.
    # The independent oracle must not mutate the later edit's original input.
    assert sum(s.Volume() for s in source.copy().cut(solid.copy()).Solids())<1e-6
    assert len(material.Faces())==len(cover['panels'])
    # Check serialized product geometry, independently of the support builder.
    # Every manufacturing face must have a positive native distance to source.
    distances=[face.distance(source) for face in material.Faces()]
    assert shape_hash(source)==source_hash
    assert min(distances)>.9999
    assert all(x['lower_bound_mm']>.9999 for x in check(cover,'positive_clearance')['observed']['panels'])
    net=generate_net(cover,dict(connection_plan='connected_15mm_v1'),output=tmp_path)
    assert not net['diagnostics'] and net['foldback']['maximum_error_mm']<1e-6
    assert any(s['kind']=='fold' for s in net['seams']) and not any(s['kind']=='cut' for s in net['seams'])
    assert len(net['overlaps'])==sum(s['kind']=='join' for s in net['seams'])>0
    assert all(t['width_mm']==15 for t in net['overlaps'])
    assert all(polygon_shape(piece['material_domain']).geom_type=='Polygon' for piece in net['pieces'])
    folded=cq.Shape.importBrep(str(tmp_path/'folded-body.brep'))
    assert folded.Area()==pytest.approx(material.Area(),abs=1e-6)
    tabs=cq.Shape.importBrep(str(tmp_path/'folded-tabs.brep'))
    assert tabs.isValid() and tabs.Area()==pytest.approx(net['areas']['overlap_mm2'],abs=1e-6)
    assert check(net,'manufacturing_approval')['status']=='needs_review'
    p['clearance_options']['clearance_mm']=2.
    after=generate(p,m,'r3-edited',previous=cover['baseline'])
    assert after['baseline']==cover['baseline'] and after['dimensions_mm']!=cover['dimensions_mm']
    corrupted=copy.deepcopy(cover['baseline']);corrupted['volume_mm3']*=1.1
    with pytest.raises(ValueError,match='baseline_integrity'):generate(p,m,'forged',previous=corrupted)


def test_large_box_cannot_replace_real_motor_complex_envelope_or_change_denominator():
    source,p,m=motor()
    base,_=close_recesses(source);b=source.BoundingBox()
    assert (b.xlen+2)*(b.ylen+2)*(b.zlen+1)/base.Volume()>1.2
    p['clearance_options']['clearance_mm']=10.
    cover=generate(p,m,'oversized')
    assert cover['status']=='failed' and check(cover,'volume_ratio')['status']=='fail'


@pytest.mark.parametrize('cuts',[[300,40],[40,40],[-100],[1000]])
def test_bad_sections_do_not_publish_a_false_positive_clearance(cuts):
    with pytest.raises(ValueError,match='invalid_native_section_cuts'):
        construct(cq.Solid.makeBox(100,70,50),1.,cuts)


def test_incomplete_equipment_and_scaling_are_not_silently_accepted():
    _,p,m=motor();p['included_faces']=[m.occurrences[0].refs[0]]
    with pytest.raises(ValueError,match='full_equipment'):generate(p,m,'partial')
    p['included_faces']=[];p['allowance']['factors']=[1.01]*3
    with pytest.raises(ValueError,match='not_scaling'):generate(p,m,'scaled')
