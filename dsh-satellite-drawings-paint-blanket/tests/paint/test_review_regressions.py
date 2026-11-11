"""Required independent-review counterexamples, all registered in B08."""
import copy
import math
import cadquery as cq
import pytest
from jsonschema import ValidationError
from b08_cases import assembly, params, box, from_shapes, override
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.selection import Budget, PaintError
from thermal_drawings.paint.contacts import threshold_interval
from thermal_drawings.paint.overrides import resolve_overrides
from thermal_drawings.domain.validation import validate as production_validate
from thermal_drawings.domain.errors import ServiceError
from contracts import validate as contract_validate


@pytest.mark.parametrize('gap,status,count',[
    (.1-1e-7,'needs_review',0),(.1+1e-7,'needs_review',0),
    (.1-1e-7-1e-9,'passed',2),(.1+1e-7+1e-9,'passed',0),
    (.1-1e-7+1e-9,'needs_review',0),(.1+1e-7-1e-9,'needs_review',0),
])
def test_both_uncertainty_endpoints_and_adjacent_gaps(gap,status,count):
    model=assembly(gap);result=generate(params(model),model,'review-threshold')
    assert result['status']==status,result['diagnostics']
    assert result['algorithm_version']=='b08-planar-v1-r1'
    assert len(result['regions'])==count
    if status=='needs_review':assert all(d['code']=='threshold_uncertain' for d in result['diagnostics'])


@pytest.mark.parametrize('deviation',[0,1e-12,5e-8,1e-7])
def test_local_deviation_endpoints_use_outward_stable_interval(deviation):
    lo,hi=threshold_interval(.1,deviation)
    for gap in [.1-(1e-7+deviation),.1+(1e-7+deviation)]:
        assert lo<=gap<=hi
    assert .1-(1e-7+deviation)-1e-9<lo
    assert .1+(1e-7+deviation)+1e-9>hi


def pocket_model(kind):
    plate=box(0,0,-5,100,80,5)
    if kind in ('blind','through','back_pockets'):
        plate=plate.cut(cq.Solid.makeCylinder(4,2 if kind!='through' else 5,cq.Vector(50,40,-2 if kind!='through' else -5)))
        if kind=='back_pockets':plate=plate.cut(cq.Solid.makeCylinder(4,2,cq.Vector(50,40,-5)))
    elif kind in ('counterbore','countersink'):
        plate=plate.cut(cq.Solid.makeCylinder(2,5,cq.Vector(50,40,-5)))
        mouth=cq.Solid.makeCylinder(4,2,cq.Vector(50,40,-2)) if kind=='counterbore' else cq.Solid.makeCone(2,4,2,cq.Vector(50,40,-2))
        plate=plate.cut(mouth)
    elif kind=='rectangular':plate=plate.cut(box(40,30,-2,20,20,2))
    return from_shapes([plate.clean()])


@pytest.mark.parametrize('kind',['blind','rectangular','back_pockets'])
def test_blind_or_obstructed_pocket_never_silently_becomes_hole(kind):
    model=pocket_model(kind);result=generate(params(model),model,'review-pocket')
    assert result['status']=='needs_review' and not result['regions']
    assert any(d['code']=='opening_classification_unknown' for d in result['diagnostics'])


@pytest.mark.parametrize('kind',['through','counterbore','countersink'])
def test_through_and_known_stepped_mouth_have_real_clear_exit(kind):
    model=pocket_model(kind);result=generate(params(model),model,'review-through')
    assert result['status']=='passed',result['diagnostics']
    assert len(result['regions'])==1 and result['regions'][0]['kind']=='hole'
    assert result['regions'][0]['area_mm2']==pytest.approx(33*math.pi,rel=1e-6)
    proof=result['regions'][0]['provenance'][0]['evidence']['passage_proofs'][0]
    assert proof['material_intersection_mm3']==0 and proof['passage_depth_mm']==pytest.approx(5)
    assert proof['classification']==('through' if kind=='through' else 'stepped_or_countersunk_through')


@pytest.mark.parametrize('policy,count',[('hole',1),('exclude',0)])
def test_blind_pocket_requires_exact_floor_override_and_reason(policy,count):
    model=pocket_model('blind');p=params(model)
    floor=next(r for o,f,r in model.faces if f.geomType()=='PLANE' and f.normalAt().z>.9 and abs(f.Center().z+2)<1e-6)
    p['overrides']=[override(floor,policy)]
    result=generate(p,model,'review-manual')
    assert result['status']=='passed',result['diagnostics']
    assert len(result['regions'])==count
    if count:
        assert result['regions'][0]['origin']=='manual'
        assert floor in result['regions'][0]['source_refs']
    p['overrides']=[override(p['target_face_refs'][0],policy)]
    result=generate(p,model,'review-wrong-face')
    assert result['status']=='needs_review' and not result['regions']


def override_pair(model):
    p=params(model)
    foot=next(r for o,f,r in model.faces if o is model.occurrences[1] and f.geomType()=='PLANE' and f.normalAt().z<-.9)
    return [override(foot,'exclude'),override(p['target_face_refs'][0],'exclude')]


def test_different_faces_cannot_share_override_id_in_schema_or_runtime():
    model=assembly();p=params(model);p['overrides']=override_pair(model)
    p['overrides'][1]['id']=p['overrides'][0]['id']
    with pytest.raises(ValidationError):contract_validate('paint',p)
    with pytest.raises(ServiceError):production_validate('paint',p)
    with pytest.raises(ServiceError):generate(p,model,'duplicate-id')
    with pytest.raises(PaintError,match='must be unique'):resolve_overrides(p['overrides'],model)
    envelope=dict(schema_version=1,module='paint',operation='paint.generate',project_id=model.model_ref['project_id'],
                  model_ref=model.model_ref,expected_revision='r',selection_refs=p['target_face_refs'],parameters=p,
                  overrides=p['overrides'],idempotency_key='duplicate-id')
    with pytest.raises(ValidationError):contract_validate('operation',envelope)
    with pytest.raises(ServiceError):production_validate('runtime',envelope,'OperationEnvelope')


def test_one_applied_override_does_not_hide_another_unused_record():
    model=assembly();p=params(model);p['overrides']=override_pair(model)
    result=generate(p,model,'partially-used')
    assert result['status']=='needs_review'
    unused=[d['observed']['override_id'] for d in result['diagnostics'] if d['code']=='override_not_applicable']
    assert unused==[p['overrides'][1]['id']]


def test_application_tracking_compares_complete_record(monkeypatch):
    import thermal_drawings.paint.pipeline as pipeline
    model=assembly();p=params(model);p['overrides']=override_pair(model)[:1]
    original=pipeline.contact_patches
    def altered(*args,**kwargs):
        patches,evidence=original(*args,**kwargs)
        for item in evidence:
            if item.get('override'):
                item['override']={**item['override'],'reason':'different override record'}
        return patches,evidence
    monkeypatch.setattr(pipeline,'contact_patches',altered)
    result=generate(p,model,'wrong-record')
    assert result['status']=='needs_review'
    assert any(d['code']=='override_not_applicable' for d in result['diagnostics'])


def test_crossing_sources_use_bounded_plane_sections_instead_of_cartesian_scans():
    model=from_shapes([box(0,0,-5,100,80,5)]+[box(5+18*i,10,-1,5,5,8) for i in range(5)])
    budget=Budget(maximum_pairs=100)
    result=generate(params(model),model,'global-budget',budget=budget)
    assert result['status']=='passed',result['diagnostics']
    assert len(result['regions'])==5
    assert budget.pairs<=100


def test_default_pair_budget_is_bounded_and_scales_to_scoped_candidates(monkeypatch):
    import thermal_drawings.paint.pipeline as pipeline
    model=assembly();observed={}
    monkeypatch.setattr(pipeline,'contact_pair_budget',lambda *args:25000)
    def contacts(target,plane,model,params,overrides,budget,diagnose):
        observed['maximum_pairs']=budget.maximum_pairs
        return [],[]
    monkeypatch.setattr(pipeline,'contact_patches',contacts)
    result=generate(params(model),model,'dynamic-budget')
    assert result['status']=='passed'
    assert observed['maximum_pairs']==25000
