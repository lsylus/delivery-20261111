"""Traceable extraction of actual equipment, never a generated box substitute."""
from pathlib import Path
import json,hashlib
import cadquery as cq
from geometry_core.xcaf import read_xcaf_source
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT.parent/'dsh-satellite-geometry/cases/satellite-assembly/original.step'
def metrics(s):
 b=s.BoundingBox();return dict(volume_mm3=s.Volume(),area_mm2=s.Area(),bounds_mm=[b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax],faces=len(s.Faces()))
def main():
 graph=read_xcaf_source(SOURCE);assembly=cq.Assembly(name='B12_original_battery_equipment');original=[]
 for key in [(1,128),(1,136),(1,147),(1,148)]:
  node=graph.node(key);geometry=graph.geometry(key);world=cq.Shape.cast(geometry.world_shape);original.append(dict(source_key=key,name=node.occurrence_name,metrics=metrics(world)))
  assembly.add(cq.Shape.cast(geometry.definition_shape),name=node.occurrence_name,loc=cq.Location(geometry.world_location))
 path=ROOT/'fixtures/real-derived/b12-battery-equipment.step';path.parent.mkdir(parents=True,exist_ok=True);assembly.save(str(path))
 derived=read_xcaf_source(path);leaves=[n for n in derived.nodes if n.is_leaf];assert len(leaves)==4
 for entry in original:
  node=next(n for n in leaves if n.occurrence_name==entry['name']);observed=metrics(cq.Shape.cast(derived.geometry(node.key).world_shape));expected=entry['metrics']
  assert observed['faces']==expected['faces']==6
  for k in ['volume_mm3','area_mm2']:assert abs(observed[k]-expected[k])<=max(1e-6,abs(expected[k])*1e-9)
  assert max(abs(a-b) for a,b in zip(observed['bounds_mm'],expected['bounds_mm']))<1e-6
  entry['derived_key']=node.key;entry['derived_metrics']=observed
 record=dict(schema_version=1,status='pass',source_path=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),source_bytes=SOURCE.stat().st_size,derived_path=str(path.relative_to(ROOT)),derived_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),derived_bytes=path.stat().st_size,equipment=original,engineering_truth='not_reviewed',scope='Four actual source battery modules, definitions/names and world placements retained. Full original assembly display import rejected for non-triangulable unrelated face; no geometry fabricated.',tolerances=dict(length_mm=1e-6,relative_area_volume=1e-9,meaning='extraction identity oracle, not manufacturing tolerance'))
 (ROOT/'fixtures/manifests/blanket_cases.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(status='pass',instances=4,bytes=path.stat().st_size)))
if __name__=='__main__':main()
