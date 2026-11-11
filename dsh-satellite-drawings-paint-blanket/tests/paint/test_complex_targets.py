from pathlib import Path
import cadquery as cq
import pytest
from thermal_drawings.paint.curved_targets import inspect_target,edge_band,feature_inventory
ROOT=Path(__file__).resolve().parents[2]
def test_tilted_plane_native_3d_domain():
 s=cq.Solid.makeBox(40,30,10).rotate((0,0,0),(1,0,0),37)
 f=max(s.Faces(),key=lambda f:f.Center().z);r=inspect_target(f,dict(entity_id='target'))
 assert r['native_area_mm2']==pytest.approx(f.Area())
 assert max(p[2] for p in r['boundaries'][0]['world_mm'])-min(p[2] for p in r['boundaries'][0]['world_mm'])>1
def test_curved_target_not_projected():
 s=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/fuel-tank.brep'))
 f=next(f for f in s.Faces() if f.geomType()=='CYLINDER');r=inspect_target(f,{})
 assert r['chart']['surface_type']=='CYLINDER' and not r['manufacturing_approved']
def test_native_feature_mouths_do_not_silently_approve():
 s=cq.Solid.makeBox(50,50,15).cut(cq.Solid.makeCylinder(4,8,cq.Vector(12,12,7))).cut(cq.Solid.makeBox(8,15,5,cq.Vector(30,10,10))).fuse(cq.Solid.makeCylinder(5,5,cq.Vector(35,35,15))).clean()
 features=feature_inventory(s)
 assert features and any(f['candidate']=='recess_or_hole' for f in features)
 assert any(f['candidate']=='boss_or_interface' for f in features)
 assert all(f['status']=='needs_review' for f in features)
def test_actual_mounting_plate_inventory():
 s=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/mounting-plate.brep'))
 assert feature_inventory(s)
def test_surface_band_measures_true_edge_distance():
 face=next(f for f in cq.Solid.makeCylinder(10,20).Faces() if f.geomType()=='CYLINDER')
 edge=next(e for e in face.Edges() if e.geomType()=='CIRCLE')
 r=edge_band(face,edge)
 assert r['metric']=='native_3d_edge_distance' and r['triangles']
 assert any(t['classification']=='unprotected' for t in r['triangles'])
 assert any(t['classification']=='boundary_uncertain' for t in r['triangles'])


@pytest.mark.parametrize('extra',[dict(cuts_u=[1.0]),dict(envelope_offset_mm=1.0)])
def test_analysis_rejects_parameters_not_supported_by_paint(extra):
 import sys
 sys.path.insert(0,str(ROOT/'tests/blanket'))
 from helpers import model_for
 from thermal_drawings.domain.complex_analysis import compute
 shape=cq.Solid.makeBox(10,10,10);model=model_for(shape)
 params=dict(face_ref=model.faces[0][2],deflection_mm=.5,cuts_u=[]);params.update(extra)
 with pytest.raises(ValueError,match='paint analysis does not accept'):
  compute(model,dict(id='r'),params,'paint')
