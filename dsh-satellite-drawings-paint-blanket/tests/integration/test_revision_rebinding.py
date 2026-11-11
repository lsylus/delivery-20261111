import copy
from thermal_drawings.domain.rebinding import entity_rebinding

def ref(instance,entity,revision=1):
 return dict(project_id='p',model_id='m',model_revision=revision,assembly_digest=str(revision)*64,instance_id=instance,entity_kind='face',entity_id=entity,
  signature=dict(type='PLANE',area_mm2=100,centroid_mm=[0,0,0],normal=[0,0,1],adjacency=['a','b']))
def test_unique_mapping_and_immutable_history():
 old=[ref('old','f')];new=[ref('new','g',2)]
 r=entity_rebinding(old,new,{'old':['new']})
 assert r['status']=='valid' and r['mappings'][0]['new_ref']==new[0]
 assert r['history']==old and old[0]['model_revision']==1
def test_duplicate_occurrences_need_explicit_unique_lineage():
 old=[ref('old','f')];new=[ref('a','g',2),ref('b','g',2)]
 r=entity_rebinding(old,new,{'old':['a','b']})
 assert r['status']=='needs_reselection' and r['mappings'][0]['new_ref'] is None
def test_duplicate_face_and_changed_geometry_do_not_replay():
 old=[ref('old','f')];new=[ref('new','g',2),ref('new','h',2)]
 assert entity_rebinding(old,new,{'old':['new']})['status']=='needs_reselection'
 new=new[:1];new[0]['signature']['centroid_mm']=[0,0,.1]
 assert entity_rebinding(old,new,{'old':['new']})['status']=='needs_reselection'
def test_many_to_one_rejected():
 old=[ref('a','f'),ref('b','f')];new=[ref('new','g',2)]
 r=entity_rebinding(old,new,{'a':['new'],'b':['new']})
 assert all(x['status']=='needs_reselection' and x['new_ref'] is None for x in r['mappings'])


def test_replay_domain_error_retains_audit_and_does_not_publish(monkeypatch,tmp_path):
 import sys,json
 from pathlib import Path
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blanket'))
 from helpers import fixture
 from thermal_drawings.domain.revision_transfer import compute
 from thermal_drawings.blanket.panels import NetError
 import thermal_drawings.blanket.net_operations as net_ops
 params,model=fixture()
 source=dict(id='old',parameters=params,document_edits=[dict(kind='blanket_net_v1')],model_ref=model.model_ref)
 def invalid(*args,**kwargs):raise NetError('fixed_point_outside_domain')
 monkeypatch.setattr(net_ops,'rebuild_net',invalid)
 audit=compute(model,model,source,dict(id='new'),'candidate','blanket',tmp_path)
 assert audit['status']=='needs_reselection' and 'fixed_point_outside_domain' in audit['reason']
 assert 'candidate' not in audit and audit['history_revision']==source
 assert json.loads((tmp_path/'rebind-analysis.json').read_text())['status']=='needs_reselection'
