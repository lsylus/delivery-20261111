"""Curved PaintResult current/edit/restore/export, preserving native holes."""
import json,sys,math,hashlib,os
from pathlib import Path
import cadquery as cq
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[1]
from b09_workflow import configured_service,head,result,completed,signature
from thermal_drawings.blanket.surface_charts import world

def exercise(directory,out):
 out.mkdir(parents=True,exist_ok=True);s=configured_service(directory)
 def perform(p,op,params=None):return completed(s,p,head(s,p),op,params)
 def save(name,value):(out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 try:
  p=s.project();shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'));face=shape.Faces()[43]
  path=directory/'motor-native-two-hole-face.step';cq.exporters.export(face,str(path))
  asset=s.call('POST',f'/projects/{p}/assets',path.read_bytes(),expected=201,headers={'Content-Type':'application/step','X-Filename':path.name})[1]
  imported=s.wait(s.submit_import(p,asset));assert imported['state']=='succeeded',imported
  a=next(a for a in imported['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'));mapping=s.call('GET','/artifacts/'+a['id'])[1];ref=mapping['faces'][0]['face_ref']
  rev=head(s,p);params=dict(schema_version=1,model_ref=rev['model_ref'],target_face_refs=[ref],scope_boundary=None,contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[],rule_version='paint-v1')
  rev=s.call('POST',f'/projects/{p}/revisions',dict(expected_revision=rev['id'],model_ref=rev['model_ref'],parameters=params,selection=[ref],overrides=[]),expected=201)[1]
  perform(p,'paint.generate',params);initial=result(s,p)
  assert initial['paint']['status']=='needs_review' and initial['paint']['candidate_editable'] and not initial['paint']['regions']
  facts=initial['paint']['evidence'][0]['boundaries'];assert len(facts)==2
  params['curved_boundary_rules']=[dict(boundary_id=b['boundary_id'],classification='hole',reason='Explicit R1 test classification of source native hole') for b in facts]
  rev=s.edit(p,head(s,p),params);perform(p,'paint.generate',params);classified=result(s,p);assert len(classified['paint']['regions'])==2
  # Native chart clear material square, independently checked against source and protection.
  doc=classified['paint']['drawing_document'];outline=[e['points'] for e in doc['entities'] if e['layer']=='OUTLINE'];material=Polygon(outline[0],outline[1:])
  for region in classified['paint']['regions']:material=material.difference(Polygon(region['loops'][0]['points'],[h['points'] for h in region['loops'][1:]]))
  q=material.buffer(-5).representative_point();polygon=list(box(q.x-2,q.y-2,q.x+2,q.y+2).exterior.coords)[:-1]
  perform(p,'paint.edit_regions',dict(result_id=classified['result_id'],action='add',points=polygon,reason='R1 manual surface patch'));edited=result(s,p)
  manual=next(r for r in edited['paint']['regions'] if r['kind']=='manual')
  perform(p,'paint.edit_regions',dict(result_id=edited['result_id'],action='move',region_id=manual['id'],delta_mm=[1,0],reason='R1 native-chart move'));moved=result(s,p)
  perform(p,'paint.edit_regions',dict(result_id=moved['result_id'],action='exclude',points=[[q.x,q.y],[q.x+1,q.y],[q.x+1,q.y+1],[q.x,q.y+1]],reason='R1 retain paint'));edited=result(s,p)
  assert edited['paint']['revision_id']==head(s,p)['id']==edited['paint']['drawing_document']['revision_id']
  regions={x['id']:x for x in edited['paint']['regions']}
  for overlay in edited['paint']['overlay']:
   region=regions[overlay['region_id']];assert region['surface_mapping']
   for ring,points in zip(region['loops'],overlay['loops_world_mm']):
    for uv,xyz in zip(ring['points'],points):
     assert math.dist(world(region['surface_mapping'],uv),xyz)<1e-7
     assert cq.Vertex.makeVertex(*xyz).distance(face)<.03
  perform(p,'drawing.edit_annotation',dict(result_id=edited['result_id'],annotation_id='r1-note',text='Native curved protection - pending approval',position=[q.x,q.y]));noted=result(s,p)
  saved=perform(p,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle');save('bundle',s.call('GET','/artifacts/'+bundle['id'])[1])
  s.stop();s.start();perform(p,'engineering.restore',dict(artifact_id=bundle['id']));restored=result(s,p)
  assert signature(restored['paint'])==signature(noted['paint'])
  exported=perform(p,'drawing.export',dict(result_id=restored['result_id'],draft=True))
  for a in exported['artifacts']:
   data=s.call('GET','/artifacts/'+a['id'],raw=True)[1];assert hashlib.sha256(data).hexdigest()==a['sha256'];(out/Path(a['relative_storage_path']).name).write_bytes(data)
  assert (out/'drawing.dwg').read_bytes()[:6]==b'AC1032'
  evidence=json.loads((out/'conversion.json').read_text());assert all(c['exit_code']==0 for c in evidence['commands']) and evidence['result_status']=='needs_review'
  for name,value in [('initial',initial),('classified',classified),('edited',edited),('restored',restored)]:save(name,value)
  record=dict(status='pass',scope='Exact source motor face 43 with two inner wires; full motor solid import remains blocked',source_asset_sha256=asset['sha256'],boundaries=facts,regions=len(restored['paint']['regions']),full_acceptance=False);save('workflow',record);return record
 finally:
  logs=out/'worker-logs';logs.mkdir(exist_ok=True)
  for f in (s.data/'jobs').glob('*.log'):(logs/f.name).write_bytes(f.read_bytes())
  s.close()
if __name__=='__main__':print(json.dumps(exercise(ROOT/'work/b13-r1-paint-http',ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r1/verification')/'r1-paint-http')))
