import pytest
import cadquery as cq
from shapely.geometry import Polygon
from shapely.ops import unary_union
from b08_cases import assembly, params, box, from_shapes
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.selection import Plane, Budget, face_polygon


def geom(region):
    return Polygon(region['loops'][0]['points'],[h['points'] for h in region['loops'][1:]])


def test_clip_to_board_hole_slot_and_explicit_scope():
    plate=box(0,0,-5,40,30,5).cut(cq.Solid.makeCylinder(3,5,cq.Vector(10,10,-5)),box(25,0,-5,4,12,5))
    m=from_shapes([plate,box(0,5,.099,15,10,5)])
    p=params(m)
    target=m.resolve(p['target_face_refs'][0])[1];plane=Plane(target)
    p['scope_boundary']=dict(points=[list(plane.uv(cq.Vector(x,y,0))) for x,y in [(0,0),(20,0),(20,30),(0,30)]],closed=True,orientation='ccw')
    r=generate(p,m,'r')
    assert r['status']=='passed',r['diagnostics']
    material=face_polygon(target,plane,Budget()).intersection(Polygon(p['scope_boundary']['points']))
    protected=unary_union([geom(x) for x in r['regions']])
    assert protected.difference(material).area<1e-9
    assert protected.area>0
    assert not protected.covers(__import__('shapely').geometry.Point(plane.uv(cq.Vector(10,10,0))))


def test_drawing_hatches_and_overlay_are_same_region_version():
    m=assembly();r=generate(params(m),m,'revision-42')
    doc=r['drawing_document']
    assert doc['revision_id']==r['revision_id']=='revision-42'
    hatches=[e for e in doc['entities'] if e['kind']=='hatch']
    assert len(hatches)==len(r['regions'])==len(r['overlay'])
    for region,hatch,overlay in zip(r['regions'],hatches,r['overlay']):
        assert region['loops']==[hatch['outer_loop'],*hatch['holes']]
        assert region['source_refs']==hatch['source_refs']==overlay['source_refs']
        assert region['id']==hatch['id']==overlay['region_id']


def test_zero_offsets_have_exact_footprint_area():
    m=assembly();p=params(m);p['contact_offset_mm']=0
    r=generate(p,m,'r')
    assert sum(x['area_mm2'] for x in r['regions'])==pytest.approx(200,rel=1e-6)


def test_generated_region_ids_cannot_rebind_to_another_revision():
    m=assembly();p=params(m);p['contact_offset_mm']=0
    a=generate(p,m,'revision-a');b=generate(p,m,'revision-b')
    assert {r['id'] for r in a['regions']}.isdisjoint({r['id'] for r in b['regions']})
    assert {e['id'] for e in a['drawing_document']['entities']}.isdisjoint({e['id'] for e in b['drawing_document']['entities']})
