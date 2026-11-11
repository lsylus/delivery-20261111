"""Archive real browser-triggered exports before removing its private service."""
import hashlib,json,sqlite3,math
from pathlib import Path
from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.profiles import DrawingProfile
from thermal_drawings.drawing.validation import validate_dxf

def archive(service,out):
 out.mkdir(parents=True,exist_ok=True);records=[];bundles=[]
 with sqlite3.connect(service.data/'engineering.sqlite3') as c:
  for body,payload in c.execute("SELECT body,payload FROM runs WHERE json_extract(body,'$.operation')='engineering.save' AND module='blanket' AND state='succeeded'"):
   job=json.loads(body);input_=json.loads(payload);bundle=next(a for a in job['artifacts'] if a['role']=='engineering_bundle');dest=out/('bundle-'+job['id']);dest.mkdir();files=[]
   def copy_asset(record,storage,name):
    raw=(service.data/storage).read_bytes();assert hashlib.sha256(raw).hexdigest()==record['sha256'] and len(raw)==record['bytes'];path=dest/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);files.append(dict(path=name,sha256=record['sha256'],bytes=len(raw)))
   copy_asset(bundle,bundle['relative_storage_path'],'engineering.json')
   value=json.loads((dest/'engineering.json').read_text());assert value['construction_parameters']['parameters'] and value['rebuilder_version']=='b11-state-v1'
   model=input_['model'];source_id=model['snapshot']['source_manifest']['asset_id'];source=json.loads(c.execute('SELECT body FROM assets WHERE id=?',(source_id,)).fetchone()[0]);copy_asset(source,source['storage'],'source.step')
   for artifact in model['artifacts']+input_['blanket_artifacts']:
    copy_asset(artifact,artifact['relative_storage_path'],artifact['relative_storage_path'])
   assert any(a['format']=='BREP' for a in model['artifacts'])
   bundles.append(dict(run_id=job['id'],revision_id=bundle['revision_id'],files=files))
  for body,payload in c.execute("SELECT body,payload FROM runs WHERE json_extract(body,'$.operation')='drawing.export' AND module='blanket' AND state='succeeded'"):
   run=json.loads(body);input_=json.loads(payload);document=input_['drawing_result']['drawing_document'];assert document['revision_id']==run['input_revision'];dest=out/run['id'];dest.mkdir()
   for a in run['artifacts']:
    data=(service.data/a['relative_storage_path']).read_bytes();assert len(data)==a['bytes'] and hashlib.sha256(data).hexdigest()==a['sha256'];(dest/Path(a['relative_storage_path']).name).write_bytes(data)
   assert (dest/'drawing.dwg').read_bytes()[:6]==b'AC1032'
   result=validate_dxf(DrawingDocument(document),dest/'drawing.readback.dxf',DrawingProfile());evidence=json.loads((dest/'conversion.json').read_text());assert evidence['revision_id']==document['revision_id'] and all(c['exit_code']==0 for c in evidence['commands'])
   (dest/'document.json').write_text(json.dumps(document,indent=2)+'\n');(dest/'run.json').write_text(json.dumps(run,indent=2)+'\n')
   records.append(dict(run_id=run['id'],revision_id=document['revision_id'],dwg_sha256=hashlib.sha256((dest/'drawing.dwg').read_bytes()).hexdigest(),readback=result,dimension_lengths_mm=sorted(round(math.dist(e['start'],e['end']),6) for e in document['entities'] if e['kind']=='dimension')))
 assert len(records)==2 and len({r['revision_id'] for r in records})==len({r['dwg_sha256'] for r in records})==2
 assert records[0]['dimension_lengths_mm']!=records[1]['dimension_lengths_mm']
 assert bundles
 record=dict(status='pass',bundles=bundles,exports=records,full_acceptance=False,autocad_reopen='not_run');(out/'summary.json').write_text(json.dumps(record,indent=2)+'\n');return record
