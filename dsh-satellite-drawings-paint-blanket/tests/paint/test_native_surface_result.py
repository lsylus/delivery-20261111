import math
from pathlib import Path
import cadquery as cq
import pytest
from b08_cases import from_shapes,params
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.blanket.surface_charts import world
ROOT=Path(__file__).resolve().parents[2]

def test_real_motor_boundary_classification_current_candidate():
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'));m=from_shapes([shape])
 ref=m.occurrences[0].refs[43];p=params(m,ref);initial=generate(p,m,'unconfirmed')
 assert initial['status']=='needs_review' and initial['candidate_editable'] and not initial['regions']
 facts=initial['evidence'][0]['boundaries'];assert len(facts)==2
 p['curved_boundary_rules']=[dict(boundary_id=f['boundary_id'],classification='hole',reason='Explicit source hole classification') for f in facts]
 actual=generate(p,m,'confirmed')
 assert actual['status']=='needs_review' and len(actual['regions'])==2
 for region,overlay in zip(actual['regions'],actual['overlay']):
  assert region['provenance'][0]['evidence']['offset_mm']==3
  for loop,points in zip(region['loops'],overlay['loops_world_mm']):
   assert all(math.dist(world(region['surface_mapping'],uv),xyz)<1e-8 for uv,xyz in zip(loop['points'],points))
 p['curved_boundary_rules'][0]['boundary_id']='boundary-'+'0'*20
 failed=generate(p,m,'stale');assert failed['status']=='failed' and failed['drawing_document'] is None

def test_tilted_plane_hole_slot_boss_protection_rotation_invariance():
 source=cq.Solid.makeBox(100,80,10).cut(cq.Solid.makeCylinder(4,10,cq.Vector(20,20,0))).cut(cq.Solid.makeBox(8,18,10,cq.Vector(40,15,0))).fuse(cq.Solid.makeCylinder(6,6,cq.Vector(75,55,10))).clean()
 results=[]
 for angle in [0,37]:
  shape=source.rotate((0,0,0),(1,0,0),angle);m=from_shapes([shape])
  ref=max((r for o,f,r in m.faces if f.geomType()=='PLANE' and f.normalAt().z>0),key=lambda r:r['signature']['area_mm2'])
  result=generate(params(m,ref),m,'tilted-'+str(angle));assert result['status']=='passed',result['diagnostics']
  kinds=[x['kind'] for x in result['regions']];assert kinds.count('hole')==2 and kinds.count('boss')==1
  assert result['drawing_document']['revision_id']==result['revision_id']
  results.append(result)
 assert sorted(r['area_mm2'] for r in results[0]['regions'])==pytest.approx(sorted(r['area_mm2'] for r in results[1]['regions']),rel=1e-7)
 assert abs(results[1]['drawing_document']['frame']['z_axis'][1])>.5
