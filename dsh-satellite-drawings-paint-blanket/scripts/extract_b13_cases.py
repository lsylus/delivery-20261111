"""Extract actual source definitions/world placements, no importer changes."""
import hashlib,json
from pathlib import Path
import cadquery as cq
from geometry_core.xcaf import read_xcaf_source
ROOT=Path(__file__).resolve().parents[1]
def metrics(s):
 b=s.BoundingBox()
 return dict(volume_mm3=s.Volume(),area_mm2=s.Area(),bounds_mm=[b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax],faces=len(s.Faces()))
def main():
 source=ROOT.parent/'dsh-satellite-geometry/cases/satellite-assembly/original.step'
 graph=read_xcaf_source(source);records=[]
 out=ROOT/'fixtures/real-derived/b13';out.mkdir(parents=True,exist_ok=True)
 for key,label in [(158,'computer-space'),(157,'launch-mechanism'),(27,'conical-support'),(124,'fuel-tank'),(4,'motor'),(137,'mounting-plate'),(142,'reaction-wheel'),(28,'camera')]:
  n=graph.node((1,key));shape=cq.Shape.cast(graph.geometry(n.key).world_shape)
  path=out/(label+'.brep');shape.exportBrep(str(path));read=cq.Shape.importBrep(str(path))
  a,b=metrics(shape),metrics(read)
  assert a['faces']==b['faces']
  assert abs(a['volume_mm3']-b['volume_mm3'])<max(1e-6,a['volume_mm3']*1e-9)
  assert max(abs(x-y) for x,y in zip(a['bounds_mm'],b['bounds_mm']))<1e-6
  records.append(dict(id=label,source_key=n.key,name=n.occurrence_name,definition=n.definition_name,path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,source_metrics=a,readback_metrics=b))
  print(label, len(shape.Faces()),flush=True)
 result=dict(schema_version=1,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_bytes=source.stat().st_size,cases=records,
  engineering_truth='pending_case_specific_review',identity_tolerance=dict(length_mm=1e-6,relative_volume=1e-9,meaning='extraction oracle only'),
  full_assembly_import='B12 failed non-triangulable face; this extraction is not full assembly import acceptance')
 (ROOT/'fixtures/manifests/complex_cases.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
