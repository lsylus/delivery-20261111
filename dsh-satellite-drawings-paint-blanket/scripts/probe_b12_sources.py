import json,hashlib
from pathlib import Path
import cadquery as cq
from geometry_core.xcaf import read_xcaf_source
r=Path(__file__).resolve().parents[1];out=r/'docs/evidence/B12/real';out.mkdir(parents=True,exist_ok=True);records=[]
for name in ['real-gearbox','real-thruster','satellite-assembly']:
 p=r.parent/'dsh-satellite-geometry/cases'/name/'original.step';g=read_xcaf_source(p);candidates=[]
 for node in g.nodes:
  if not node.is_leaf:continue
  shape=cq.Shape.cast(g.geometry(node.key).world_shape);solids=shape.Solids()
  if len(solids)!=1:continue
  faces=solids[0].outerShell().Faces()
  if len(faces)==6 and all(f.geomType()=='PLANE' and len(f.Edges())==4 and not f.innerWires() for f in faces):
   candidates.append(dict(key=node.key,name=node.occurrence_name,definition=node.definition_name,volume=solids[0].Volume(),faces=[dict(center=f.Center().toTuple(),normal=f.normalAt().toTuple(),area=f.Area()) for f in faces]))
 records.append(dict(source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,leaves=sum(n.is_leaf for n in g.nodes),candidates=candidates));(out/'source-scan.json').write_text(json.dumps(records,indent=2)+'\n');print(name,len(candidates),flush=True)
 if candidates:break
