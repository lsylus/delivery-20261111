"""Actual STEP, HTTP, isolated workers, revision transfer and native bundles."""
import json,sys,copy
from pathlib import Path
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from workflow import Service,current,result,run
def import_shape(service,project,shape,expected='empty',name='complex.step'):
 path=service.directory/name;cq.exporters.export(shape,str(path))
 asset=service.call('POST',f'/projects/{project}/assets',path.read_bytes(),who='blanket',expected=201,headers={'Content-Type':'application/step','X-Filename':name})[1]
 job=service.wait(service.submit_import(project,asset,expected=expected,who='blanket'),'blanket')
 assert job['state']=='succeeded',job
 rev=current(service,project);model=service.call('GET',f'/projects/{project}/models/'+rev['model_ref']['model_id'],who='blanket')[1]
 map_asset=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))
 mapping=service.call('GET','/artifacts/'+map_asset['id'],who='blanket')[1]
 return rev,model,mapping
def exercise(directory,archive=None):
 service=Service(directory,timeout=120,upload_limit=8*1024*1024)
 try:
  project=service.project('blanket')
  shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/computer-space.brep'))
  rev,model,mapping=import_shape(service,project,shape)
  params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());params.update(model_ref=rev['model_ref'],
   target_instances=sorted({f['face_ref']['instance_id'] for f in mapping['faces']}),envelope_policy='orthogonal_sections_v1')
  b=shape.BoundingBox();params['installation_frame']['origin']=[b.xmin,b.ymin,b.zmin];params['allowance']['factors']=[1.01]*3
  rev=service.edit(project,rev,params,who='blanket')
  generated=run(service,project,rev,'blanket.generate',params);cover=result(service,project)
  assert cover['blanket']['status']=='needs_review' and cover['blanket']['candidate_editable']
  netrun=run(service,project,rev,'blanket.unfold',dict(result_id=cover['result_id'],settings=dict(connection_plan='connected_15mm_v1')))
  rev=current(service,project);net=service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
  assert len(net['net']['pieces'])>5 and net['net']['foldback']['maximum_error_mm']<1e-6
  from shapely.geometry import Polygon
  panel=net['net']['panels'][0];uv=list(Polygon(panel['outer_loop']['points']).representative_point().coords)[0]
  run(service,project,rev,'blanket.edit_fixed_points',dict(result_id=net['result_id'],command=dict(action='add',id='b13-preserved-point',panel_key=panel['key'],uv_mm=list(uv))))
  rev=current(service,project);net=service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
  analysis=run(service,project,rev,'geometry.analyze',dict(face_ref=mapping['faces'][0]['face_ref'],deflection_mm=.5,cuts_u=[]))
  assert current(service,project)['id']==rev['id']
  assert service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]['result_id']==net['result_id']
  saved=run(service,project,rev,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
  bundle_data=service.call('GET','/artifacts/'+bundle['id'],who='blanket')[1]
  assert bundle_data['source_manifest_refs'] and bundle_data['derived_shape_refs']
  service.stop();service.start()
  restored=run(service,project,rev,'engineering.restore',dict(artifact_id=bundle['id']))
  rev=current(service,project);source_revision=rev
  assert service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]['net']['fixed_points'][0]['id']=='b13-preserved-point'
  new,_,_=import_shape(service,project,shape,expected=rev['id'],name='revision.step')
  transferred=run(service,project,new,'engineering.rebind',dict(source_revision_id=source_revision['id']))
  after=current(service,project);assert after['id']!=new['id'] and after['model_ref']==new['model_ref']
  net_after=service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
  assert net_after['net']['fixed_points'][0]['id']=='b13-preserved-point' and net_after['net']['fixed_points'][0]['status']=='valid'
  report_asset=next(a for a in transferred['artifacts'] if a['role']=='revision_rebinding')
  report=service.call('GET','/artifacts/'+report_asset['id'],who='blanket')[1]
  assert report['status']=='valid' and report['history_revision']==source_revision
  # Repeated coincident occurrences must not be picked by index or old ID.
  compound=cq.Compound.makeCompound([shape,shape.copy()])
  ambiguous,_,_=import_shape(service,project,compound,expected=after['id'],name='ambiguous.step')
  rejected=run(service,project,ambiguous,'engineering.rebind',dict(source_revision_id=after['id']))
  rejected_report=service.call('GET','/artifacts/'+next(a for a in rejected['artifacts'] if a['role']=='revision_rebinding')['id'],who='blanket')[1]
  assert rejected_report['status']=='needs_reselection'
  assert current(service,project)['id']==ambiguous['id']
  assert service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1] is None
  # Foreign face data cannot run against this source revision.
  bad=service.operation(project,ambiguous,'geometry.analyze',dict(face_ref=mapping['faces'][0]['face_ref'],deflection_mm=.5,cuts_u=[]),who='blanket',expected=409)
  records=dict(status='pass',project=project,source_revision=source_revision['id'],rebound_revision=after['id'],
   complex_panels=len(cover['blanket']['panels']),pieces=len(net['net']['pieces']),baseline_volume_mm3=cover['blanket']['baseline']['volume_mm3'],
   unique_rebind='valid',coincident_instances='needs_reselection',point_id='b13-preserved-point',
   bundle_source_refs=bundle_data['source_manifest_refs'],ports=service.ports,resources_created=[str(directory)],resources_cleaned=[str(directory)])
  if archive:
   archive.mkdir(parents=True,exist_ok=True)
   for name,value in [('workflow',records),('cover',cover),('net',net),('bundle',bundle_data),('rebind',report),('ambiguous',rejected_report)]:
    (archive/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
   for job in [generated,netrun,saved,transferred,analysis]:
    for a in job['artifacts']:
     if a['format'] not in ('JSON','BREP','GLB'):continue
     path=archive/'artifacts'/a['run_id']/a['relative_storage_path'].split('/',2)[2];path.parent.mkdir(parents=True,exist_ok=True)
     path.write_bytes(service.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1])
  return records
 finally:service.close()
if __name__=='__main__':
 import os
 out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13')
 print(json.dumps(exercise(ROOT/'work/b13-http-isolated',out/'http')))
