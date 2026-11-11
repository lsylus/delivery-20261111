"""Real motor radial features: native footprints, chart edits, restore and DWG."""
import json,hashlib,os,math
from pathlib import Path
import cadquery as cq
from shapely.geometry import Polygon,box
from b09_workflow import configured_service,head,result,completed,signature
from thermal_drawings.blanket.surface_charts import world
ROOT=Path(__file__).resolve().parents[1]


def exercise(directory,out):
 out.mkdir(parents=True,exist_ok=True);s=configured_service(directory)
 def save(name,value):(out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 def perform(p,op,params=None):return completed(s,p,head(s,p),op,params)
 def archive(job,label):
  dest=out/label;dest.mkdir(exist_ok=True)
  for a in job['artifacts']:
   data=s.call('GET','/artifacts/'+a['id'],raw=True)[1];assert hashlib.sha256(data).hexdigest()==a['sha256'];(dest/Path(a['relative_storage_path']).name).write_bytes(data)
  return dest
 try:
  p=s.project();source=ROOT/'fixtures/real-derived/b13/motor.brep';shape=cq.Shape.importBrep(str(source));path=directory/'complete-motor.step';cq.exporters.export(shape,str(path))
  asset=s.call('POST',f'/projects/{p}/assets',path.read_bytes(),expected=201,headers={'Content-Type':'application/step','X-Filename':path.name})[1]
  imported=s.wait(s.submit_import(p,asset));assert imported['state']=='succeeded',imported;archive(imported,'import')
  a=next(a for a in imported['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'));mapping=s.call('GET','/artifacts/'+a['id'])[1];assert len(mapping['faces'])==44
  ref=max((x['face_ref'] for x in mapping['faces'] if x['face_ref']['signature']['type']=='CYLINDER'),key=lambda r:r['signature']['area_mm2'])
  rev=head(s,p);params=dict(schema_version=1,model_ref=rev['model_ref'],target_face_refs=[ref],scope_boundary=None,contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[],rule_version='paint-v1')
  s.call('POST',f'/projects/{p}/revisions',dict(expected_revision=rev['id'],model_ref=rev['model_ref'],parameters=params,selection=[ref],overrides=[]),expected=201)
  perform(p,'paint.generate',params);unconfirmed=result(s,p);save('unconfirmed',unconfirmed)
  assert not unconfirmed['paint']['regions'];facts=unconfirmed['paint']['evidence'][0]['boundaries'];assert len(facts)==2
  params['curved_boundary_rules']=[dict(boundary_id=f['boundary_id'],classification='boss',reason='Real motor outward radial feature: geometric candidate only, engineering classification and process approval pending') for f in facts]
  s.edit(p,head(s,p),params);archive(perform(p,'paint.generate',params),'native');initial=result(s,p);save('initial',initial)
  assert len(initial['paint']['regions'])==8 and {d['code'] for d in initial['paint']['diagnostics']}=={'surface_manufacturing_approval'}
  # Explicit geometry-only parameter variant, not an engineer-approved extra band.
  params['boss_additional_offset_mm']=3.;s.edit(p,head(s,p),params);archive(perform(p,'paint.generate',params),'offset-native');offset=result(s,p);save('offset-3mm',offset)
  assert sum(r['area_mm2'] for r in offset['paint']['regions'])>sum(r['area_mm2'] for r in initial['paint']['regions'])
  params['boss_additional_offset_mm']=0.;s.edit(p,head(s,p),params);perform(p,'paint.generate',params);initial=result(s,p)
  region=next(r for r in initial['paint']['regions'] if r['surface_mapping']['kind']=='PLANE' and r['area_mm2']>150)
  geom=Polygon(region['loops'][0]['points'],[h['points'] for h in region['loops'][1:]]);x,y=geom.representative_point().coords[0]
  square=box(x-.25,y-.25,x+.25,y+.25);assert geom.contains(square)
  points=[list(v) for v in list(square.exterior.coords)[:-1]];original_area=sum(r['area_mm2'] for r in initial['paint']['regions'])
  perform(p,'paint.edit_regions',dict(result_id=initial['result_id'],action='exclude',points=points,reason='Geometry-only exclusion in the actual stepped shoulder chart'));excluded=result(s,p);save('excluded',excluded)
  assert math.isclose(sum(r['area_mm2'] for r in excluded['paint']['regions']),original_area-.25,abs_tol=1e-7)
  perform(p,'paint.edit_regions',dict(result_id=excluded['result_id'],action='add',points=points,reason='Restore explicit protection candidate'));edited=result(s,p)
  manual=next(r for r in edited['paint']['regions'] if r['kind']=='manual')
  perform(p,'paint.edit_regions',dict(result_id=edited['result_id'],action='move',region_id=manual['id'],delta_mm=[.1,0],reason='Move within the actual shoulder surface'));edited=result(s,p)
  for overlay in edited['paint']['overlay']:
   reg=next(r for r in edited['paint']['regions'] if r['id']==overlay['region_id'])
   for loop,xyzs in zip(reg['loops'],overlay['loops_world_mm']):
    for uv,xyz in zip(loop['points'],xyzs):assert math.dist(world(reg['surface_mapping'],uv),xyz)<1e-7
  save('edited',edited);saved=perform(p,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');archive(saved,'bundle')
  s.stop();s.start();archive(perform(p,'engineering.restore',dict(artifact_id=bundle['id'])),'restored-native');restored=result(s,p)
  assert signature(restored['paint'])==signature(edited['paint']);save('restored',restored)
  dest=archive(perform(p,'drawing.export',dict(result_id=restored['result_id'],draft=True)),'export')
  assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
  ev=json.loads((dest/'conversion.json').read_text());assert all(c['exit_code']==0 for c in ev['commands']) and ev['result_status']=='needs_review'
  value=dict(status='pass',case='motor',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_face_count=44,target_face_ref=ref,boundary_ids=[f['boundary_id'] for f in facts],native_bosses=initial['paint']['evidence'][0]['boundaries'],regions=len(restored['paint']['regions']),manufacturing_status='needs_review',engineering_classification_approved=False,full_acceptance=False,scope='Two real inclined radial attachments with actual sidewall/shoulder/cap charts; explicit geometry candidates, no process approval')
  save('workflow',value);return value
 finally:
  logs=out/'worker-logs';logs.mkdir(exist_ok=True)
  for f in (s.data/'jobs').glob('*.log'):(logs/f.name).write_bytes(f.read_bytes())
  s.close()

if __name__=='__main__':
 base=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r3/http-development')
 value=exercise(ROOT/'work/b13-r3-paint-http',base/'paint-http');print(json.dumps({k:value[k] for k in ['status','case','regions','manufacturing_status']}))
