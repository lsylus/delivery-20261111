"""Native curved boss/contact HTTP, chart edits, restart, restore and real ODA."""
import json,sys,math,hashlib,os
from pathlib import Path
import cadquery as cq
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[1]
from b09_workflow import configured_service,head,result,completed,signature
from thermal_drawings.blanket.surface_charts import world

def sleeve(radius,z,y):
 return cq.Solid.makeCylinder(radius+3,10,cq.Vector(0,0,z)).cut(cq.Solid.makeCylinder(radius,10,cq.Vector(0,0,z))).intersect(cq.Solid.makeBox(20,50,10,cq.Vector(-10,y,z)))

def exercise(directory,out):
 out.mkdir(parents=True,exist_ok=True);s=configured_service(directory);records=[]
 def perform(p,op,params=None):return completed(s,p,head(s,p),op,params)
 def save(name,value):(out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 def archive(job,label):
  dest=out/label;dest.mkdir(exist_ok=True)
  for a in job['artifacts']:
   data=s.call('GET','/artifacts/'+a['id'],raw=True)[1];assert hashlib.sha256(data).hexdigest()==a['sha256'];(dest/Path(a['relative_storage_path']).name).write_bytes(data)
  return dest
 try:
  for name in ['boss','contacts']:
   p=s.project();base=cq.Solid.makeCylinder(30,60);path=directory/(name+'.step');assembly=cq.Assembly()
   if name=='boss':
    raised=cq.Solid.makeCylinder(36,20,cq.Vector(0,0,20)).cut(cq.Solid.makeCylinder(29,20,cq.Vector(0,0,20))).intersect(cq.Solid.makeBox(20,50,20,cq.Vector(-10,0,20)))
    assembly.add(base.fuse(raised).clean(),name='target')
   else:
    assembly.add(base,name='target');assembly.add(sleeve(30.099,10,0),name='contact-a');assembly.add(sleeve(30.099,35,-50),name='contact-b')
   assembly.export(str(path))
   asset=s.call('POST',f'/projects/{p}/assets',path.read_bytes(),expected=201,headers={'Content-Type':'application/step','X-Filename':path.name})[1]
   imported=s.wait(s.submit_import(p,asset));assert imported['state']=='succeeded',imported;archive(imported,name+'-import')
   a=next(a for a in imported['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'));mapping=s.call('GET','/artifacts/'+a['id'])[1]
   ref=max((x['face_ref'] for x in mapping['faces'] if x['face_ref']['signature']['type']=='CYLINDER'),key=lambda r:r['signature']['area_mm2'])
   rev=head(s,p);params=dict(schema_version=1,model_ref=rev['model_ref'],target_face_refs=[ref],scope_boundary=None,contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[],rule_version='paint-v1')
   rev=s.call('POST',f'/projects/{p}/revisions',dict(expected_revision=rev['id'],model_ref=rev['model_ref'],parameters=params,selection=[ref],overrides=[]),expected=201)[1]
   job=perform(p,'paint.generate',params);initial=result(s,p);save(name+'-initial',initial)
   if name=='boss':
    facts=initial['paint']['evidence'][0]['boundaries'];assert len(facts)==1
    params['curved_boundary_rules']=[dict(boundary_id=facts[0]['boundary_id'],classification='boss',reason='Explicit native raised cap classification')]
    s.edit(p,head(s,p),params);job=perform(p,'paint.generate',params)
   classified=result(s,p);archive(job,name+'-native');save(name+'-classified',classified)
   regions=classified['paint']['regions'];assert regions and classified['paint']['candidate_editable']
   if name=='contacts':assert len({f['source_refs'][1]['instance_id'] for f in classified['paint']['evidence'][0]['contacts']})==2
   region=regions[0];geom=Polygon(region['loops'][0]['points'],[h['points'] for h in region['loops'][1:]]);x,y=geom.representative_point().coords[0]
   points=[list(p) for p in list(box(x-1,y-1,x+1,y+1).exterior.coords)[:-1]]
   perform(p,'paint.edit_regions',dict(result_id=classified['result_id'],action='exclude',points=points,reason='Remove protection in the selected native chart'));excluded=result(s,p)
   save(name+'-excluded',excluded)
   assert math.isclose(sum(r['area_mm2'] for r in excluded['paint']['regions']),sum(r['area_mm2'] for r in regions)-4,rel_tol=0,abs_tol=1e-7)
   perform(p,'paint.edit_regions',dict(result_id=excluded['result_id'],action='add',points=points,reason='Restore manual protection in the selected native chart'));edited=result(s,p)
   manual=next(r for r in edited['paint']['regions'] if r['kind']=='manual')
   perform(p,'paint.edit_regions',dict(result_id=edited['result_id'],action='move',region_id=manual['id'],delta_mm=[.25,0],reason='Move protection within its retained native surface chart'));edited=result(s,p)
   assert all(r['surface_mapping']==region['surface_mapping'] for r in edited['paint']['regions'])
   for overlay in edited['paint']['overlay']:
    reg=next(r for r in edited['paint']['regions'] if r['id']==overlay['region_id'])
    for loop,xyzs in zip(reg['loops'],overlay['loops_world_mm']):
     for xy,xyz in zip(loop['points'],xyzs):assert math.dist(world(reg['surface_mapping'],xy),xyz)<1e-7
   save(name+'-edited',edited);perform(p,'drawing.edit_annotation',dict(result_id=edited['result_id'],annotation_id='r2-note',text='Native curved protection candidate',position=[x,y]));noted=result(s,p)
   saved=perform(p,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');archive(saved,name+'-bundle')
   s.stop();s.start();perform(p,'engineering.restore',dict(artifact_id=bundle['id']));restored=result(s,p)
   assert signature(restored['paint'])==signature(noted['paint']);save(name+'-restored',restored)
   dest=archive(perform(p,'drawing.export',dict(result_id=restored['result_id'],draft=True)),name+'-export')
   assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
   ev=json.loads((dest/'conversion.json').read_text());assert all(c['exit_code']==0 for c in ev['commands']) and ev['result_status']=='needs_review'
   records.append(dict(case=name,status='pass',regions=len(restored['paint']['regions']),manufacturing_status=restored['paint']['status']))
   save('workflow-progress',records)
  value=dict(status='pass',cases=records,full_acceptance=False);save('workflow',value);return value
 finally:
  logs=out/'worker-logs';logs.mkdir(exist_ok=True)
  for f in (s.data/'jobs').glob('*.log'):(logs/f.name).write_bytes(f.read_bytes())
  s.close()
if __name__=='__main__':print(json.dumps(exercise(ROOT/'work/b13-r2-paint-http',ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r2/http-development')/'r2-paint-http')))
