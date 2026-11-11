"""R2 complete-source native manufacturing candidates through real HTTP workers and ODA."""
import json,sys,hashlib,math,os
from pathlib import Path
import cadquery as cq
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from b12_workflow import configured,signature
from b13_workflow import import_shape
from workflow import current,result,run
from net_workflow import current_net

def exercise(directory,out,cases=None):
 out.mkdir(parents=True,exist_ok=True);s=configured(directory);records=[]
 def save(label,value):(out/(label+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 def perform(p,op,params=None):return run(s,p,current(s,p),op,params)
 def archive_job(job,label,who='blanket'):
  dest=out/label;dest.mkdir(exist_ok=True)
  for a in job['artifacts']:
   data=s.call('GET','/artifacts/'+a['id'],who=who,raw=True)[1];assert hashlib.sha256(data).hexdigest()==a['sha256']
   (dest/Path(a['relative_storage_path']).name).write_bytes(data)
  return dest
 try:
  for name,kind in (cases or [('computer-space',None),('motor','CYLINDER'),('conical-support','CONE'),('fuel-tank','SPHERE'),('fuel-tank-atlas','SPHERE')]):
   p=s.project('blanket');source_name='fuel-tank' if name=='fuel-tank-atlas' else name
   shape=cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{source_name}.brep'))
   scope='Full original occurrence STEP import; manufacturing scope is the selected native face' if kind else 'Full original occurrence'
   rev,model,mapping=import_shape(s,p,shape,name=name+'.step')
   archive_job(dict(artifacts=model['artifacts']),name+'-import')
   assert len(mapping['faces'])==len(shape.Faces())
   audit=json.loads((out/(name+'-import')/'tessellation-audit.json').read_text());save(name+'-import-audit',audit)
   params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());params['model_ref']=rev['model_ref']
   refs=[x['face_ref'] for x in mapping['faces']]
   if kind:
    ref=max((r for r in refs if r['signature']['type']==kind),key=lambda r:r['signature']['area_mm2'])
    params.update(envelope_policy='native_surface_v1',included_faces=[ref],target_instances=[ref['instance_id']]);params['allowance']['factors']=[1,1,1]
   else:
    params.update(envelope_policy='orthogonal_sections_v1',target_instances=sorted({r['instance_id'] for r in refs}));params['allowance']['factors']=[1.01]*3
    b=shape.BoundingBox();params['installation_frame']['origin']=[b.xmin,b.ymin,b.zmin]
   if name=='fuel-tank-atlas':params['surface_options']=dict(partition_plan='cube_greatcircle_v1',rotation_deg=[0,0,23],chart_chord_mm=.02)
   perform(p,'blanket.generate',params);cover=result(s,p);assert cover['blanket']['status']=='needs_review'
   job=perform(p,'blanket.unfold',dict(result_id=cover['result_id'],settings=dict(connection_plan='connected_15mm_v1')));archive_job(job,name+'-native')
   n=current_net(s,p);assert n['net']['overlaps'] and not n['net']['diagnostics'];save(name+'-initial-net',n)
   if kind=='SPHERE':
    for tab in n['net']['overlaps']:
     width=tab['surface_width_measurement'];assert width['acceptance']=='pass'
     assert max(abs(w-15) for w in width['native_circle_widths_mm']+width['native_cap_lengths_mm'])<1e-6 and width['native_outside_receiving_area_mm2']<1e-6
   panel=n['net']['panels'][0];domain=Polygon(panel['outer_loop']['points'],[h['points'] for h in panel['holes']]);uv=list(domain.representative_point().coords)[0]
   perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',id='r2-anchor',panel_key=panel['key'],uv_mm=list(uv))))
   n=current_net(s,p);moved=list(domain.intersection(box(uv[0]-.5,uv[1]-.5,uv[0]+1,uv[1]+1)).representative_point().coords)[0]
   perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='move',id='r2-anchor',panel_key=panel['key'],uv_mm=list(moved))))
   n=current_net(s,p);perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',id='r2-delete',panel_key=panel['key'],uv_mm=list(uv))))
   n=current_net(s,p);perform(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='delete',id='r2-delete')))
   n=current_net(s,p);seam=next(x for x in n['net']['seams'] if x['kind']=='join')
   perform(p,'blanket.edit_seams',dict(result_id=n['result_id'],seams=[dict(id=seam['id'],kind='cut',width_mm=0,overlap_owner_panel=None)]))
   n=current_net(s,p);assert next(x for x in n['net']['seams'] if x['id']==seam['id'])['kind']=='cut'
   perform(p,'blanket.edit_seams',dict(result_id=n['result_id'],seams=[{k:seam[k] for k in ('id','kind','width_mm','overlap_owner_panel')}]))
   n=current_net(s,p);perform(p,'drawing.edit_annotation',dict(result_id=n['result_id'],annotation_id='r2-note',text='R2 candidate - approval pending',position=[0,0]))
   n=current_net(s,p);saved=perform(p,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');archive_job(saved,name+'-bundle')
   before=signature(n['net']);s.stop();s.start();perform(p,'engineering.restore',dict(artifact_id=bundle['id']));n=current_net(s,p)
   assert signature(n['net'])==before and n['net']['status']=='needs_review'
   exported=perform(p,'drawing.export',dict(result_id=n['result_id'],draft=True));dest=archive_job(exported,name+'-export')
   assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
   ev=json.loads((dest/'conversion.json').read_text());assert all(c['exit_code']==0 for c in ev['commands']) and not ev['full_acceptance']
   assert ev['result_status']=='needs_review' and ev['acceptance_checks']
   save(name+'-restored-net',n)
   if name=='fuel-tank-atlas':
    assert len(n['net']['pieces'])==5 and len(n['net']['overlaps'])==8
   if kind:
    old=n;cover=result(s,p);bounds=cover['blanket']['panels'][0]['surface_mapping']['uv_bounds'];cut=bounds[0]+.4*(bounds[1]-bounds[0])
    perform(p,'blanket.edit_shape',dict(result_id=cover['result_id'],baseline_id=cover['blanket']['baseline']['id'],surface_options=dict(partition_plan='cube_greatcircle_v1',rotation_deg=[0,0,0],chart_chord_mm=.02) if name=='fuel-tank-atlas' else dict(cuts_u=[cut],chart_chord_mm=.02)))
    assert current_net(s,p) is None
    s.operation(p,current(s,p),'drawing.export',dict(result_id=old['result_id'],draft=True),who='blanket',expected=409)
   records.append(dict(case=name,status='pass',scope=scope,panels=len(n['net']['panels']),joins=sum(x['kind']=='join' for x in n['net']['seams']),folds=sum(x['kind']=='fold' for x in n['net']['seams']),overlaps=len(n['net']['overlaps']),foldback=n['net']['foldback'],manufacturing_status=n['net']['status']))
   save('workflow-progress',records)
  save('workflow',dict(status='pass',cases=records,full_acceptance=False));return records
 finally:
  logs=out/'worker-logs';logs.mkdir(exist_ok=True)
  for f in (s.data/'jobs').glob('*.log'):(logs/f.name).write_bytes(f.read_bytes())
  s.close()
if __name__=='__main__':print(json.dumps(exercise(ROOT/'work/b13-r2-http',ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r2/http-development')/'r2-http')))
