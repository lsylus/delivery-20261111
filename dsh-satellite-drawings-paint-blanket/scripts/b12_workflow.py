"""B12 exact document, history, persistence and real converter checks through HTTP."""
import json,hashlib,sys,copy,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from workflow import Service,setup,current,result,run
from net_workflow import current_net

def configured(directory):
 s=Service(directory,timeout=240,upload_limit=128*1024*1024);s.stop();c=json.loads(s.config.read_text());c['converter_config']=str(ROOT/'work/config/converters.local.json');s.config.write_text(json.dumps(c));s.start();return s

def signature(net):
 return dict(areas=net['areas'],seams=net['seams'],points=[{k:p[k] for k in ('id','panel_key','uv_mm','position3d')} for p in net['fixed_points']],entities=[{k:v for k,v in e.items() if k!='id'} for e in net['drawing_document']['entities']])

def exercise(directory,out):
 out.mkdir(parents=True,exist_ok=True);s=configured(directory);runs=[]
 def perform(p,op,params=None):
  value=run(s,p,current(s,p),op,params);runs.append(value);return value
 def save(name,value):(out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 def export(p,label):
  n=current_net(s,p);rev=current(s,p);job=perform(p,'drawing.export',dict(result_id=n['result_id'],draft=True));dest=out/label;dest.mkdir()
  for a in job['artifacts']:
   b=s.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1];assert hashlib.sha256(b).hexdigest()==a['sha256'];assert a['revision_id']==rev['id'];(dest/Path(a['relative_storage_path']).name).write_bytes(b)
  assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
  ev=json.loads((dest/'conversion.json').read_text());assert all(x['exit_code']==0 for x in ev['commands']);assert ev['revision_id']==rev['id'] and ev['draft'] and not ev['full_acceptance']
  (dest/'document.json').write_text(json.dumps(n['net']['drawing_document'],indent=2)+'\n')
  return dict(revision=rev['id'],dwg_sha256=hashlib.sha256((dest/'drawing.dwg').read_bytes()).hexdigest(),drawing=n['net']['drawing_document'])
 try:
  p,rev,_,model=setup(s)
  # Initial selection failure cannot replace the prior imported/current head.
  badparams=copy.deepcopy(rev['parameters']);badparams['target_instances']=['missing-instance']
  bad=s.wait(s.operation(p,rev,'blanket.generate',badparams,who='blanket')['run_id'],'blanket');assert bad['state']=='failed' and current(s,p)==rev
  perform(p,'blanket.generate',rev['parameters']);cover=result(s,p);baseline=cover['blanket']['baseline']
  perform(p,'blanket.unfold',dict(result_id=cover['result_id']));n=current_net(s,p)
  # Annotation must survive later net edits, undo, close/restart, restore and DWG.
  perform(p,'drawing.edit_annotation',dict(result_id=n['result_id'],annotation_id='note',text='Blanket B12 editable note',position=[10,10]));n=current_net(s,p)
  perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',id='b12-anchor',panel_key='z+',uv_mm=[50,50])));n=current_net(s,p)
  assert any(e.get('text')=='Blanket B12 editable note' for e in n['net']['drawing_document']['entities'])
  before=current(s,p);old=n
  perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='move',id='b12-anchor',panel_key='z+',uv_mm=[55,50])));moved=current_net(s,p)
  perform(p,'history.undo');assert current(s,p)==before and signature(current_net(s,p)['net'])==signature(old['net'])
  perform(p,'history.redo');assert signature(current_net(s,p)['net'])==signature(moved['net'])
  # Invalid domain retains exact old head, 3D and document.
  rev=current(s,p);n=current_net(s,p);cover=result(s,p)
  bad=s.wait(s.operation(p,rev,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='move',id='b12-anchor',panel_key='z+',uv_mm=[1000,1000])),who='blanket')['run_id'],'blanket')
  assert bad['state']=='failed' and not bad['artifacts'] and current(s,p)==rev and current_net(s,p)==n and result(s,p)==cover;save('rejected',bad)
  saved=perform(p,'engineering.save');a=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');bundle=s.call('GET','/artifacts/'+a['id'],who='blanket')[1];save('bundle',bundle)
  assert bundle['derived_shape_refs'] and bundle['source_manifest_refs'] and bundle['construction_parameters']['parameters']==rev['parameters']
  s.stop();s.start();assert current(s,p)==rev
  perform(p,'engineering.restore',dict(artifact_id=a['id']));n=current_net(s,p)
  assert n['net']['fixed_points'][0]['id']=='b12-anchor' and signature(n['net'])==signature(moved['net'])
  restored=current(s,p);perform(p,'history.undo');assert current(s,p)==rev;perform(p,'history.redo');assert current(s,p)==restored
  first=export(p,'first-export')
  oldnet=current_net(s,p);cover=result(s,p)
  perform(p,'blanket.edit_shape',dict(result_id=cover['result_id'],baseline_id=baseline['id'],dimensions_mm=[106,105,105],openings=[dict(id='port',panel='z+',loop=dict(points=[[20,20],[30,20],[30,30],[20,30]],closed=True,orientation='ccw'))]))
  assert current_net(s,p) is None and result(s,p)['blanket']['baseline']==baseline
  s.operation(p,current(s,p),'drawing.export',dict(result_id=oldnet['result_id'],draft=True),who='blanket',expected=409)
  cover=result(s,p);perform(p,'blanket.unfold',dict(result_id=cover['result_id']));n=current_net(s,p)
  hole=s.wait(s.operation(p,current(s,p),'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',panel_key='z+',uv_mm=[25,25])),who='blanket')['run_id'],'blanket');assert hole['state']=='failed'
  second=export(p,'changed-export');assert first['revision']!=second['revision'] and first['dwg_sha256']!=second['dwg_sha256']
  lengths=lambda d:sorted(round(__import__('math').dist(e['start'],e['end']),6) for e in d['entities'] if e['kind']=='dimension')
  assert lengths(first['drawing'])!=lengths(second['drawing'])
  # Same project, shared model, independent paint history and same-owner other session.
  paint=s.bind(p,'alice');paintrev=s.call('POST',f'/projects/{p}/revisions',dict(expected_revision='empty',model_ref=current(s,p)['model_ref'],selection=[],parameters={},overrides=[]),expected=201)[1]
  paintrev2=s.edit(p,paintrev,{'tag':'paint-only'});blanket_head=current(s,p)
  job=s.wait(s.operation(p,paintrev2,'history.undo')['run_id']);assert job['state']=='succeeded';assert current(s,p)==blanket_head
  s.call('GET',f'/projects/{p}/blanket-net',expected=403)
  s.operation(p,current(s,p),'drawing.export',dict(result_id=current_net(s,p)['result_id'],draft=True),who='other_session',expected=403)
  # Corrupt source/BRep/bundle never restores or changes the old head.
  bundle_path=s.data/a['relative_storage_path'];original=bundle_path.read_bytes();bundle_path.write_bytes(original+b' ')
  corrupt=s.wait(s.operation(p,current(s,p),'engineering.restore',dict(artifact_id=a['id']),who='blanket')['run_id'],'blanket')
  assert corrupt['state']=='failed' and not corrupt['artifacts'];assert current(s,p)==blanket_head;bundle_path.write_bytes(original)
  n=current_net(s,p);save('final-net',n);save('final-cover',result(s,p));save('runs',runs)
  record=dict(status='pass',project=p,baseline=baseline,first_export={k:v for k,v in first.items() if k!='drawing'},changed_export={k:v for k,v in second.items() if k!='drawing'},runs=len(runs),resources_created=[str(directory)],resources_cleaned=[str(directory)],full_acceptance=False)
  save('workflow',record);return record
 finally:s.close()
