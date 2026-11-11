import copy
import cadquery as cq
import pytest
from b08_cases import assembly, params, override, from_shapes
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.selection import Budget
from thermal_drawings.domain.errors import ServiceError
from geometry_core.solid_pairs import FacePatchIntersection


@pytest.mark.parametrize('budget',[Budget(maximum_pairs=0),Budget(maximum_points=0),Budget(timeout_s=0)])
def test_budget_no_partial_empty_pass(budget):
    m=assembly();r=generate(params(m),m,'r',budget=budget)
    assert r['status']=='needs_review' and r['regions']==[] and r['drawing_document'] is None
    assert r['diagnostics'][0]['code']=='budget_exhausted'


def test_kernel_failure_retains_failure(monkeypatch):
    import thermal_drawings.paint.contacts as contacts
    monkeypatch.setattr(contacts,'intersect_face_patches',lambda *a,**k:FacePatchIntersection(False,(),'face_intersection','Injected native failure'))
    m=assembly();r=generate(params(m),m,'r')
    assert r['status']=='failed' and not r['regions'] and not r['overlay']


def test_late_kernel_failure_discards_first_successful_foot(monkeypatch):
    import thermal_drawings.paint.contacts as contacts
    original=contacts.intersect_face_patches
    calls=[]
    def fail_later(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs) if len(calls)<=2 else FacePatchIntersection(False,(),'face_intersection','late failure')
    monkeypatch.setattr(contacts,'intersect_face_patches',fail_later)
    m=assembly();r=generate(params(m),m,'r')
    assert len(calls)==3 and r['status']=='failed' and not r['regions'] and r['drawing_document'] is None


def test_unused_override_requires_review_instead_of_silent_ignore():
    m=assembly();p=params(m);p['overrides']=[override(p['target_face_refs'][0],'exclude')]
    r=generate(p,m,'r')
    assert r['status']=='needs_review' and any(d['code']=='override_not_applicable' for d in r['diagnostics'])


def test_native_cylinder_uses_surface_chart_and_requires_review():
    m=from_shapes([cq.Solid.makeCylinder(5,10)])
    ref=next(r for o,f,r in m.faces if f.geomType()=='CYLINDER')
    r=generate(params(m,ref),m,'r')
    assert r['status']=='needs_review' and r['candidate_editable']
    assert r['surface_mapping']['kind']=='CYLINDER' and r['surface_mapping']['mapping_type']=='isometric'
    assert r['drawing_document']['revision_id']=='r'
    assert any(c['reason']=='surface_manufacturing_approval' and c['status']=='needs_review' for c in r['checks'])
    outline=next(e for e in r['drawing_document']['entities'] if e['layer']=='OUTLINE')
    assert max(x for x,y in outline['points'])-min(x for x,y in outline['points'])==pytest.approx(10*__import__('math').pi)


@pytest.mark.parametrize('failure',['stale_ref','ambiguous','foreign','duplicate_target','invalid_scope','stale_override'])
def test_invalid_selection_and_override_never_rebind(failure):
    m=assembly();p=params(m)
    ref=next(r for o,f,r in m.faces if o is m.occurrences[1] and f.normalAt().z<-.9)
    value=override(copy.deepcopy(ref),'exclude')
    p['overrides']=[value]
    if failure=='stale_ref':p['target_face_refs'][0]=dict(p['target_face_refs'][0],model_revision=2)
    if failure=='foreign':p['model_ref']=dict(p['model_ref'],project_id='foreign')
    if failure=='ambiguous':p['overrides'].append({**copy.deepcopy(value),'id':'different-id-same-face'})
    if failure=='duplicate_target':p['target_face_refs']*=2
    if failure=='invalid_scope':p['scope_boundary']=dict(points=[[0,0],[10,10],[10,0],[0,10]],closed=True,orientation='ccw')
    if failure=='stale_override':value['model_revision']=2
    r=generate(p,m,'r')
    assert r['status']!='passed' and not r['regions']


@pytest.mark.parametrize('key,value',[('contact_threshold_mm',float('nan')),('contact_offset_mm',-1),('contact_comparison','le'),('overrides',[{}])])
def test_contract_rejects_invalid_input(key,value):
    m=assembly();p=params(m);p[key]=value
    with pytest.raises(ServiceError):generate(p,m,'r')
