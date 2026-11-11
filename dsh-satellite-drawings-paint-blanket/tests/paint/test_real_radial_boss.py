from pathlib import Path
import copy
import math
import cadquery as cq
import pytest
from b08_cases import from_shapes,params
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.surface_pipeline import boundary_id
from thermal_drawings.blanket.surface_charts import world
from thermal_drawings.paint.selection import Budget

ROOT=Path(__file__).resolve().parents[2]


def actual_motor(angle=0):
    source=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
    if angle:source=source.rotate((0,0,0),(1,2,3),angle).translate((13,-11,7))
    model=from_shapes([source])
    target=max((f for f in source.Faces() if f.geomType()=='CYLINDER'),key=lambda f:f.Area())
    ref=next(r for _,f,r in model.faces if abs(f.Area()-target.Area())<1e-5)
    p=params(model,ref)
    p['curved_boundary_rules']=[dict(boundary_id=boundary_id(w),classification='boss',reason='Actual radial motor feature geometry candidate; process approval pending') for w in target.innerWires()]
    return model,p


@pytest.mark.parametrize('angle',[0,31])
def test_actual_two_motor_radial_bosses_include_caps_shoulders_and_sidewalls(angle,tmp_path):
    model,p=actual_motor(angle);r=generate(p,model,'real-motor',output=tmp_path)
    assert r['status']=='needs_review' and r['candidate_editable'],r['diagnostics']
    assert {d['code'] for d in r['diagnostics']}=={'surface_manufacturing_approval'}
    assert len(r['regions'])==8
    assert {x['surface_mapping']['kind'] for x in r['regions']}=={'PLANE','CYLINDER'}
    facts=r['evidence'][0]['boundaries'];assert len(facts)==2
    assert all(len(f['native_boss']['component_faces'])==4 for f in facts)
    native=cq.Shape.importBrep(str(tmp_path/'paint-native-footprints.brep'))
    assert native.isValid() and len(native.Faces())==2
    assert native.Area()==pytest.approx(sum(f['native_boss']['native_mouth_area_mm2'] for f in facts),abs=1e-6)
    for region in r['regions']:
        face=model.resolve(region['source_refs'][-1])[1]
        assert region['area_mm2']==pytest.approx(face.Area(),rel=.002)
        proof=region['provenance'][0]['evidence'];distances=[]
        for loop in region['loops']:
            for xy in loop['points']:
                point=cq.Vector(*world(region['surface_mapping'],xy));distances.append(cq.Vertex.makeVertex(*point.toTuple()).distance(face))
                if face.geomType()=='CYLINDER':
                    from OCP.BRepAdaptor import BRepAdaptor_Surface
                    cylinder=BRepAdaptor_Surface(face.wrapped).Cylinder();axis=cq.Vector(cylinder.Axis().Direction().Coord());origin=cq.Vector(cylinder.Location().Coord())
                    assert (point-origin).cross(axis).Length==pytest.approx(cylinder.Radius(),abs=1e-7)
        assert max(distances)==pytest.approx(proof['boundary_vertex_native_distance_max_mm'],abs=1e-7)
        assert max(distances)<=proof['source_edge_tolerance_mm']+r['numerical_policy']['chord_mm']
        assert not proof['manufacturing_approved']


def test_no_engineering_classification_is_fabricated_and_budget_fails_closed():
    model,p=actual_motor();unconfirmed=copy.deepcopy(p);unconfirmed.pop('curved_boundary_rules')
    r=generate(unconfirmed,model,'unconfirmed');assert not r['regions']
    assert any(d['code']=='curved_opening_classification' for d in r['diagnostics'])
    r=generate(p,model,'budget',budget=Budget(maximum_pairs=20))
    assert not r['regions'] and r['drawing_document'] is None
    for rule in p['curved_boundary_rules']:rule['classification']='exclude'
    assert not generate(p,model,'excluded')['regions']


def test_recess_tagged_boss_cannot_be_protected_as_outward_geometry():
    base=cq.Solid.makeCylinder(30,60)
    pocket=cq.Solid.makeCylinder(5,20,cq.Vector(0,20,30),cq.Vector(0,1,0))
    source=base.cut(pocket).clean();model=from_shapes([source])
    ref=max((r for _,f,r in model.faces if f.geomType()=='CYLINDER'),key=lambda r:r['signature']['area_mm2'])
    p=params(model,ref);target=model.resolve(ref)[1]
    p['curved_boundary_rules']=[dict(boundary_id=boundary_id(w),classification='boss',reason='Deliberately wrong classification must not fabricate a cap') for w in target.innerWires()]
    r=generate(p,model,'negative')
    assert not r['regions'] and any(d['code']=='curved_boss_native_cap_unsupported' for d in r['diagnostics'])
