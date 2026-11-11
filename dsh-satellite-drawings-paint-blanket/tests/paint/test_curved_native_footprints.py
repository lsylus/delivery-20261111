import math
import cadquery as cq
import pytest
from b08_cases import from_shapes,params
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.blanket.surface_charts import world
from thermal_drawings.paint.selection import Budget

def sleeve(radius,height,z,x=-10,y=0,dx=20,dy=50):
 return cq.Solid.makeCylinder(radius+3,height,cq.Vector(0,0,z)).cut(cq.Solid.makeCylinder(radius,height,cq.Vector(0,0,z))).intersect(cq.Solid.makeBox(dx,dy,height,cq.Vector(x,y,z)))

def target_ref(model):return max((r for o,f,r in model.faces if o is model.occurrences[0] and f.geomType()=='CYLINDER'),key=lambda r:r['signature']['area_mm2'])

@pytest.mark.parametrize('angle',[0,37])
def test_curved_boss_has_native_footprint_and_actual_cap_mapping(angle,tmp_path):
 base=cq.Solid.makeCylinder(30,60);raised=cq.Solid.makeCylinder(36,20,cq.Vector(0,0,20)).cut(cq.Solid.makeCylinder(29,20,cq.Vector(0,0,20))).intersect(cq.Solid.makeBox(20,50,20,cq.Vector(-10,0,20)))
 shape=base.fuse(raised).clean().rotate((0,0,0),(1,0,0),angle).moved(cq.Location(cq.Vector(13,-17,29)));model=from_shapes([shape]);p=params(model,target_ref(model));first=generate(p,model,'initial')
 assert len(first['evidence'][0]['boundaries'])==1
 p['curved_boundary_rules']=[dict(boundary_id=first['evidence'][0]['boundaries'][0]['boundary_id'],classification='boss',reason='Confirmed integral raised curved cap')]
 result=generate(p,model,'boss',output=tmp_path);assert result['candidate_editable'],result['diagnostics']
 boss=next(x for x in result['regions'] if x['kind']=='boss');proof=boss['provenance'][0]['evidence'];assert proof['native_projected_footprint_area_mm2']>0
 assert proof['normal_gap']['gap_mm']==pytest.approx(6)
 cap=model.resolve(proof['source_cap_ref'])[1]
 assert boss['area_mm2']==pytest.approx(cap.Area(),rel=1e-4)
 assert boss['surface_mapping']['radius_mm']==pytest.approx(36)
 for loop in boss['loops']:
  for xy in loop['points']:assert cq.Vertex.makeVertex(*world(boss['surface_mapping'],xy)).distance(cap)<1e-6
 assert cq.Shape.importBrep(str(tmp_path/'paint-native-footprints.brep')).isValid()
 from thermal_drawings.paint.commands import prepare_edit
 from thermal_drawings.drawing.document_edits import apply_edits
 from shapely.geometry import Polygon,box
 g=Polygon(boss['loops'][0]['points']);x,y=g.representative_point().coords[0]
 revision=dict(id='edit',model_ref=model.model_ref,selection=p['target_face_refs'])
 command=prepare_edit('paint.edit_regions',dict(result_id='r',action='exclude',points=[list(x) for x in list(box(x-1,y-1,x+1,y+1).exterior.coords)[:-1]],reason='Test native cap chart edit'),result,revision)
 edited=apply_edits(result,dict(revision,document_edits=[command]))
 assert sum(r['area_mm2'] for r in edited['regions'])==pytest.approx(boss['area_mm2']-4)
 assert all(r['surface_mapping']==boss['surface_mapping'] for r in edited['regions'])
 for region in edited['regions']:
  for loop in region['loops']:
   for xy in loop['points']:assert cq.Vertex.makeVertex(*world(region['surface_mapping'],xy)).distance(cap)<1e-6
 p['curved_boundary_rules'][0]['classification']='exclude';assert not generate(p,model,'exclude')['regions']

@pytest.mark.parametrize('gap,expected',[(.099,2),(.1,0),(.101,0)])
def test_multi_occurrence_native_curved_contacts_threshold_and_mapping(gap,expected,tmp_path):
 base=cq.Solid.makeCylinder(30,60)
 sources=[base,sleeve(30+gap,10,10),sleeve(30+gap,10,35,y=-50)]
 model=from_shapes(sources);p=params(model,target_ref(model));result=generate(p,model,'contacts',output=tmp_path)
 assert result.get('candidate_editable'),result['diagnostics']
 facts=result['evidence'][0]['contacts'];assert len(facts)==expected
 assert len({f['source_refs'][1]['instance_id'] for f in facts})==expected
 for fact in facts:
  assert fact['normal_gap']['gap_mm']==pytest.approx(gap) and fact['native_footprint_area_mm2']>0
 for region in result['regions']:
  assert region['kind']=='contact'
  for loop in region['loops']:
   for xy in loop['points']:assert cq.Vertex.makeVertex(*world(region['surface_mapping'],xy)).distance(model.resolve(p['target_face_refs'][0])[1])<1e-6
 if gap==.1:assert any(d['code']=='threshold_uncertain' for d in result['diagnostics'])


def test_curved_scan_budget_never_publishes_partial_protection():
 model=from_shapes([cq.Solid.makeCylinder(30,60),sleeve(30.099,10,10)])
 result=generate(params(model,target_ref(model)),model,'budget',budget=Budget(maximum_pairs=0))
 assert not result['regions'] and result['drawing_document'] is None
 assert any(d['code']=='budget_exhausted' for d in result['diagnostics'])

@pytest.mark.parametrize('kind',['CONE','SPHERE'])
def test_native_cone_and_sphere_contact_projection_with_true_trim(kind,tmp_path):
 gap=.099
 if kind=='CONE':
  radial=gap/math.cos(math.atan(10/60))
  base=cq.Solid.makeCone(30,40,60,angleDegrees=90)
  source=cq.Solid.makeCone(34+radial,44+radial,60,angleDegrees=90).cut(cq.Solid.makeCone(30+radial,40+radial,60,angleDegrees=90))
 else:
  base=cq.Solid.makeSphere(30,angleDegrees1=-30,angleDegrees2=30,angleDegrees3=90)
  source=cq.Solid.makeSphere(34,angleDegrees1=-20,angleDegrees2=20,angleDegrees3=90).cut(cq.Solid.makeSphere(30+gap,angleDegrees1=-90,angleDegrees2=90))
 model=from_shapes([base,source]);ref=next(r for o,f,r in model.faces if o is model.occurrences[0] and f.geomType()==kind)
 result=generate(params(model,ref),model,'analytic-contact',output=tmp_path)
 assert result.get('candidate_editable'),result['diagnostics']
 facts=result['evidence'][0]['contacts'];assert len(facts)==1,result['diagnostics']
 assert facts[0]['normal_gap']['gap_mm']==pytest.approx(gap)
 target=model.resolve(ref)[1];footprint=cq.Shape.importBrep(str(tmp_path/'paint-native-footprints.brep'))
 assert footprint.isValid() and footprint.Area()>0
 assert footprint.cut(target).Area()<1e-6
 assert any(r['kind']=='contact' for r in result['regions'])
