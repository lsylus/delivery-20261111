"""Complete real motor -> positive-clearance cover -> connected net -> ODA DWG."""
import json,sys,hashlib,os,math
from pathlib import Path
import cadquery as cq
from shapely.geometry import Polygon,shape as polygon_shape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from b12_workflow import configured,signature
from b13_workflow import import_shape
from workflow import current,result,run
from net_workflow import current_net


def exercise(directory,out):
 out.mkdir(parents=True,exist_ok=True);s=configured(directory)
 def save(label,value):(out/(label+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 def perform(p,op,params=None):
  with (out/'events.jsonl').open('a') as f:f.write(json.dumps(dict(event='start',operation=op))+'\n')
  value=run(s,p,current(s,p),op,params)
  with (out/'events.jsonl').open('a') as f:f.write(json.dumps(dict(event='finished',operation=op,run_id=value['id'] if 'id' in value else value.get('run_id'),state=value['state']))+'\n')
  return value
 def archive(job,label):
  dest=out/label;dest.mkdir(exist_ok=True)
  for a in job['artifacts']:
   data=s.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1];assert hashlib.sha256(data).hexdigest()==a['sha256']
   (dest/Path(a['relative_storage_path']).name).write_bytes(data)
  return dest
 try:
  p=s.project('blanket');source=ROOT/'fixtures/real-derived/b13/motor.brep';original=cq.Shape.importBrep(str(source))
  rev,model,mapping=import_shape(s,p,original,name='complete-motor.step');archive(dict(artifacts=model['artifacts']),'import')
  refs=[x['face_ref'] for x in mapping['faces']];assert len(refs)==44
  params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());b=original.BoundingBox()
  params.update(model_ref=rev['model_ref'],target_instances=sorted({r['instance_id'] for r in refs}),envelope_policy='faceted_clearance_v1',clearance_options=dict(clearance_mm=1.,section_cuts_mm=[40.,300.,334.]))
  params['installation_frame']['origin']=[b.xmin,b.ymin,b.zmin];params['allowance']['factors']=[1,1,1]
  archive(perform(p,'blanket.generate',params),'initial-cover');cover=result(s,p);baseline=cover['blanket']['baseline'];save('initial-cover',cover)
  assert cover['blanket']['status']=='needs_review' and len(cover['blanket']['panels'])>5
  archive(perform(p,'blanket.unfold',dict(result_id=cover['result_id'],settings=dict(connection_plan='connected_15mm_v1'))),'initial-native')
  n=current_net(s,p);save('initial-net',n)
  assert not n['net']['diagnostics'] and all(x['kind']!='cut' for x in n['net']['seams'])
  assert all(polygon_shape(piece['material_domain']).geom_type=='Polygon' for piece in n['net']['pieces'])
  assert n['net']['overlaps'] and all(t['width_mm']==15 for t in n['net']['overlaps'])
  panel=max(n['net']['panels'],key=lambda q:Polygon(q['outer_loop']['points']).area)
  domain=Polygon(panel['outer_loop']['points'],[h['points'] for h in panel['holes']]);uv=list(domain.representative_point().coords)[0]
  perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',id='r3-anchor',panel_key=panel['key'],uv_mm=list(uv))))
  n=current_net(s,p);moved=[uv[0]+.25,uv[1]];assert domain.contains(__import__('shapely').geometry.Point(moved))
  perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='move',id='r3-anchor',panel_key=panel['key'],uv_mm=moved)))
  n=current_net(s,p);seam=next(x for x in n['net']['seams'] if x['kind']=='join')
  perform(p,'blanket.edit_seams',dict(result_id=n['result_id'],seams=[dict(id=seam['id'],kind='cut',width_mm=0,overlap_owner_panel=None)]))
  n=current_net(s,p);assert next(x for x in n['net']['seams'] if x['id']==seam['id'])['kind']=='cut'
  perform(p,'blanket.edit_seams',dict(result_id=n['result_id'],seams=[{k:seam[k] for k in ('id','kind','width_mm','overlap_owner_panel')}]))
  n=current_net(s,p);save('edited-net',n);before=signature(n['net'])
  saved=perform(p,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');archive(saved,'bundle')
  s.stop();s.start();archive(perform(p,'engineering.restore',dict(artifact_id=bundle['id'])),'restored-native');n=current_net(s,p)
  assert signature(n['net'])==before and n['net']['status']=='needs_review'
  assert result(s,p)['blanket']['baseline']==baseline
  assert n['net']['fixed_points'][0]['id']=='r3-anchor' and n['net']['fixed_points'][0]['status']=='valid'
  save('restored-net',n);dest=archive(perform(p,'drawing.export',dict(result_id=n['result_id'],draft=True)),'export')
  assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
  conversion=json.loads((dest/'conversion.json').read_text());assert all(c['exit_code']==0 for c in conversion['commands']) and conversion['result_status']=='needs_review'
  old=n;cover=result(s,p)
  s.operation(p,current(s,p),'blanket.edit_shape',dict(result_id=cover['result_id'],baseline_id='foreign',clearance_options=dict(clearance_mm=2.,section_cuts_mm=[40.,300.,334.])),who='blanket',expected=409)
  archive(perform(p,'blanket.edit_shape',dict(result_id=cover['result_id'],baseline_id=baseline['id'],clearance_options=dict(clearance_mm=2.,section_cuts_mm=[40.,300.,334.]))),'clearance-edited')
  after=result(s,p);save('clearance-edited-cover',after);assert after['blanket']['baseline']==baseline and current_net(s,p) is None
  s.operation(p,current(s,p),'drawing.export',dict(result_id=old['result_id'],draft=True),who='blanket',expected=409)
  value=dict(status='pass',case='motor',scope='Full original 44-face occurrence; no clipping or face selection; positive-clearance connected manufacturing candidate',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),panels=len(n['net']['panels']),pieces=len(n['net']['pieces']),joins=len(n['net']['overlaps']),folds=sum(x['kind']=='fold' for x in n['net']['seams']),foldback=n['net']['foldback'],baseline=baseline,model_revision_unchanged=after['blanket']['model_ref']==rev['model_ref'],full_acceptance=False,manufacturing_status='needs_review')
  save('workflow',value);return value
 finally:
  logs=out/'worker-logs';logs.mkdir(exist_ok=True)
  for f in (s.data/'jobs').glob('*.log'):(logs/f.name).write_bytes(f.read_bytes())
  s.close()

if __name__=='__main__':
 base=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r3/http-development')
 value=exercise(ROOT/'work/b13-r3-blanket-http',base/'blanket-http');print(json.dumps({k:value[k] for k in ['status','panels','pieces','joins','folds']}))
