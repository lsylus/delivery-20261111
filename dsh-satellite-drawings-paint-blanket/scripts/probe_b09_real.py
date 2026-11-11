"""Read existing STEP candidate; record exact selected plane and unknown truth."""
import tempfile,json,hashlib,shutil
from pathlib import Path
from b09_workflow import ROOT,configured_service,head,completed,result

SOURCE=ROOT.parent/'dsh-satellite-geometry/cases/real-gearbox/original.step'
def main():
 base=Path(tempfile.mkdtemp(prefix='b09-real-',dir=ROOT/'work'));s=None
 out=ROOT/'docs/evidence/B09/real';out.mkdir(parents=True,exist_ok=True)
 try:
  s=configured_service(base/'service');p=s.project();data=SOURCE.read_bytes()
  a=s.call('POST',f'/projects/{p}/assets',data,expected=201,headers={'Content-Type':'application/step','X-Filename':'gearbox.step'})[1]
  run=s.wait(s.submit_import(p,a));assert run['state']=='succeeded',run
  rev=head(s,p)
  a=next(a for a in run['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))
  mapping=json.loads(s.call('GET',a['download_url'].removeprefix('/api/v1'),raw=True)[1]);refs=[f['face_ref'] for f in mapping['faces']]
  candidates=sorted([r for r in refs if r['signature']['type']=='PLANE'],key=lambda r:-r['signature']['area_mm2'])
  # Explicit developer-selected technical candidate. No claim of engineer approval.
  (out/'planes.json').write_text(json.dumps([r['signature'] for r in candidates],indent=2)+'\n')
  target=next((r for r in candidates if len(r['signature']['adjacency'])==4),candidates[-1])
  params=dict(schema_version=1,model_ref=rev['model_ref'],target_face_refs=[target],scope_boundary=None,contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[],rule_version='paint-v1')
  rev=s.call('POST',f'/projects/{p}/revisions',dict(expected_revision=rev['id'],model_ref=rev['model_ref'],selection=[target],parameters=params,overrides=[]),expected=201)[1]
  generated=completed(s,p,rev,'paint.generate',params);paint=result(s,p)
  (out/'probe-diagnostics.json').write_text(json.dumps(paint,indent=2)+'\n')
  assert paint and paint['paint']['drawing_document'] is not None
  doc=paint['paint']['drawing_document']
  from shapely.geometry import Polygon
  from shapely.ops import unary_union
  # Find a clear reference square *inside* actual material, in local millimetres.
  outlines=[e['points'] for e in doc['entities'] if e['kind']=='polyline']
  material=Polygon()
  for pts in outlines:
   area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(pts,pts[1:]+pts[:1]))
   if area>0:material=material.union(Polygon(pts))
  for pts in outlines:
   area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(pts,pts[1:]+pts[:1]))
   if area<0:material=material.difference(Polygon(pts))
  for r in paint['paint']['regions']:
   if r['local_frame']==doc['frame']:material=material.difference(Polygon(r['loops'][0]['points'],[l['points'] for l in r['loops'][1:]]))
  center=material.representative_point();half=min(center.distance(material.boundary)/3,2);assert half>1e-4
  x,y=center.x,center.y;points=[[x-half,y-half],[x+half,y-half],[x+half,y+half],[x-half,y+half]]
  (out/'candidate.json').write_text(json.dumps(dict(status='pass',source_path=str(SOURCE),source_sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),target=target,target_index=refs.index(target),reference_points=points,reference_area_mm2=4*half*half,generated_status=paint['paint']['status'],engineering_truth='not_reviewed',zip_dwg_correspondence='unknown',revision=rev,run=generated),indent=2)+'\n')
  (out/'initial-paint.json').write_text(json.dumps(paint['paint'],indent=2)+'\n')
  print(json.dumps(dict(status=paint['paint']['status'],target=target['signature'],reference_points=points)))
 finally:
  if s:s.close()
  shutil.rmtree(base)
if __name__=='__main__':main()
