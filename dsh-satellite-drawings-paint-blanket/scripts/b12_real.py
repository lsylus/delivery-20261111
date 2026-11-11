import json,time,hashlib
from pathlib import Path
from b12_workflow import ROOT,current
SOURCE=ROOT/'fixtures/real-derived/b12-battery-equipment.step'
def import_real(s,out):
 p=s.project('blanket');data=SOURCE.read_bytes();a=s.call('POST',f'/projects/{p}/assets',data,who='blanket',expected=201,headers={'Content-Type':'application/step','X-Filename':'satellite-assembly.step'})[1]
 id_=s.submit_import(p,a,who='blanket');deadline=time.monotonic()+1000
 while time.monotonic()<deadline:
  job=s.call('GET','/runs/'+id_,who='blanket')[1]
  if job['state'] in ('succeeded','failed','cancelled'):break
  time.sleep(.25)
 out.mkdir(parents=True,exist_ok=True)
 (out/'import-run.json').write_text(json.dumps(job,indent=2)+'\n')
 for log in (s.data/'jobs').glob('*.log'):(out/('import-'+log.name)).write_text(log.read_text())
 assert job['state']=='succeeded',job
 rev=current(s,p);model=s.call('GET',f'/projects/{p}/models/'+rev['model_ref']['model_id'],who='blanket')[1]
 a=next(x for x in model['artifacts'] if x['relative_storage_path'].endswith('mesh-map.json'));mapping=s.call('GET','/artifacts/'+a['id'],who='blanket')[1]
 # Candidate is fixed by audited original occurrence name and six exact planes.
 instance=next(i for i in model['snapshot']['instances'] if i['name']=='Tesla_Battery_Module_6.25kWh,_3_in_series_for_required_volts_v4_2')
 refs=[f['face_ref'] for f in mapping['faces']];faces=[f for f in refs if f['instance_id']==instance['instance_id']];assert len(faces)==6 and all(f['signature']['type']=='PLANE' for f in faces)
 bottom=min(faces,key=lambda f:f['signature']['centroid_mm'][2]);assert bottom['signature']['normal'][2]<-.999
 record=dict(status='pass',source_path=str(SOURCE),source_sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),project=p,revision=rev,instance=instance,faces=faces,bottom_index=refs.index(bottom),face_indices=[refs.index(f) for f in faces],assembly_instances=len(model['snapshot']['instances']),engineering_truth='not_reviewed',source_provenance=json.loads((ROOT/'fixtures/manifests/blanket_cases.json').read_text()),scope='Actual extracted equipment assembly with verified source geometry and world placements; technical selection, not manufacturing approval')
 out.mkdir(parents=True,exist_ok=True);(out/'candidate.json').write_text(json.dumps(record,indent=2)+'\n');return p,rev,record
