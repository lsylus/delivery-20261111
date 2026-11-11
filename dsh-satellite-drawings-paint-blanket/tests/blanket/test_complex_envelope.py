import copy
from pathlib import Path
import cadquery as cq
import pytest
from helpers import fixture,check,model_for,ROOT
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.complex_envelopes import profiles,solid_from_profiles
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.seams import adjacency

def source(kind):
 if kind=='step':return cq.Solid.makeBox(100,80,40).fuse(cq.Solid.makeBox(45,80,30,cq.Vector(0,0,40))).clean()
 if kind=='interface':return cq.Solid.makeBox(100,80,60).fuse(cq.Solid.makeBox(30,20,20,cq.Vector(100,30,20))).clean()
 return cq.Solid.makeBox(100,30,60).fuse(cq.Solid.makeBox(30,70,60,cq.Vector(0,30,0))).clean()
def params(shape,factor=1.01):
 p,m=fixture(shape=shape);p['envelope_policy']='orthogonal_sections_v1';p['allowance']['factors']=[factor]*3
 return p,m
@pytest.mark.parametrize('kind',['step','interface','concave'])
def test_contains_with_fixed_concave_denominator_and_multicut(kind,tmp_path):
 s=source(kind);p,m=params(s);r=generate(p,m,'a',tmp_path)
 assert r['status']=='needs_review' and r['candidate_editable']
 assert r['baseline']['volume_mm3']==pytest.approx(s.Volume())
 assert len(r['panels'])>5
 assert check(r,'coverage')['observed']['outside_volume_mm3']<1e-6
 _,seams=adjacency(r['panels'])
 net=generate_net(r,dict(fold_seam_ids=[],cut_seam_ids=[s['id'] for s in seams]))
 assert net['status']=='needs_review' and net['candidate_editable'] and len(net['pieces'])==len(r['panels'])
 assert net['foldback']['maximum_error_mm']<1e-6
 p['allowance']['factors']=[1.02]*3
 r2=generate(p,m,'b',previous=r['baseline']);assert r2['baseline']==r['baseline']
def test_hollow_volume_is_exterior_space():
 s=source('concave').cut(cq.Solid.makeBox(10,10,50,cq.Vector(10,10,10))).clean()
 p,m=params(s,1);r=generate(p,m,'a')
 assert r['baseline']['volume_mm3']>s.Volume()+4900
 assert r['baseline']['parameters']['closure_policy']
def test_ratio_cannot_be_rescued_by_baseline_resize():
 p,m=params(source('concave'),1.5);r=generate(p,m,'a')
 assert r['status']=='failed' and check(r,'volume_ratio')['status']=='fail'
 old=copy.deepcopy(r['baseline']);old['volume_mm3']*=2
 with pytest.raises(ValueError,match='baseline_integrity'):generate(p,m,'b',previous=old)
def test_real_computer_space_expected_native_sections():
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/computer-space.brep'))
 b=shape.BoundingBox();local=shape.translate((-b.xmin,-b.ymin,-b.zmin))
 p,m=params(local);r=generate(p,m,'a')
 assert r['status']=='needs_review' and r['candidate_editable']
 assert r['baseline']['volume_mm3']==pytest.approx(56812500,rel=1e-9)
 assert r['baseline']['volume_mm3']<425*400*500*.8
 assert len(r['panels'])>5
def test_opening_and_extreme_factor_fail_without_rewriting_baseline():
 p,m=params(source('step'));r=generate(p,m,'a')
 p['openings']=[dict(id='bad',panel='complex-'+'0'*18,loop=dict(points=[[0,0],[1,0],[1,1]],closed=True,orientation='ccw'))]
 with pytest.raises(ValueError,match='needs_reselection'):generate(p,m,'b',previous=r['baseline'])
 p['openings']=[];p['allowance']['factors']=[float('inf'),1,1]
 from thermal_drawings.domain.errors import ServiceError
 with pytest.raises(ServiceError):generate(p,m,'c')

def test_true_motor_interface_offset_not_uniform_scale_or_box():
 from thermal_drawings.blanket.exterior import offset_candidate,scaled_candidate
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
 _,_,bad=scaled_candidate(shape)
 assert bad['containment']=='fail'  # Ratio alone cannot certify protrusions.
 baseline,cover,material,record=offset_candidate(shape,1.)
 assert baseline.Volume()==pytest.approx(5637234.35462044,rel=1e-9)
 assert baseline.Volume()>shape.Volume()
 assert record['checks']['containment']['outside_volume_mm3']<1e-6
 assert record['checks']['penetration']['crossing_area_mm2']<1e-8
 assert 1<=record['volume_ratio']<=1.2
 assert len(material.Faces())+record['evaluation_only_caps']==len(cover.Faces())
 assert record['manufacturing_faces']>5

def test_real_launch_cavity_closed_for_evaluation_not_material_denominator():
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/launch-mechanism.brep'))
 b=shape.BoundingBox();p,m=params(shape.translate((-b.xmin,-b.ymin,-b.zmin)),1.01)
 r=generate(p,m,'launch')
 assert r['baseline']['volume_mm3']==pytest.approx(70*70*350)
 assert r['baseline']['volume_mm3']>shape.Volume()*1.9

@pytest.mark.parametrize('factors',[[1,1.01,1],[1.01,1,1],[1,1,1.01]])
def test_anisotropic_extremes_keep_containment(factors):
 p,m=params(source('concave'));p['allowance']['factors']=factors
 r=generate(p,m,'anisotropic');assert r['status']=='needs_review' and r['candidate_editable']


def test_real_connected_plan_and_unapproved_checks():
 from thermal_drawings.blanket.seam_plans import propose
 from thermal_drawings.blanket.panels import NetError
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/computer-space.brep'))
 b=shape.BoundingBox();p,m=params(shape.translate((-b.xmin,-b.ymin,-b.zmin)));r=generate(p,m,'connected')
 assert check(r,'local_clearance')['status']=='needs_review'
 assert check(r,'unfolding')['status']=='not_run'
 default=generate_net(r)
 assert default['status']=='failed'
 assert any(d['code']=='connected_seam_plan_available' for d in default['diagnostics'])
 plan=propose(r);net=generate_net(r,plan['settings'])
 assert not net['diagnostics'] and net['foldback']['maximum_error_mm']<1e-6
 assert sum(s['kind']=='fold' for s in net['seams'])==1
 assert sum(s['kind']=='join' for s in net['seams'])==19
 assert len(net['overlaps'])==19 and all(t['width_mm']==15 and t['relief_mm'] for t in net['overlaps'])
 assert check(net,'unfolding')['status']=='pass' and check(net,'local_clearance')['status']=='needs_review'
 chosen=next(s for s in net['seams'] if s['kind']=='join')
 intent=dict(plan['settings']);intent['seam_overrides']=[dict(id=chosen['id'],kind='cut',overlap_owner_panel=None,width_mm=0)]
 updated=propose(r,intent);after=generate_net(r,updated['settings'])
 assert next(s for s in after['seams'] if s['id']==chosen['id'])['kind']=='cut'
 with pytest.raises(NetError):propose(r,dict(fold_seam_ids=[s['id'] for s in net['seams']]))
