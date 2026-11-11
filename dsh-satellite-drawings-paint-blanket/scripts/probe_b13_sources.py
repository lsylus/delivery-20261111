"""Read-only source survey; exact native shapes retained under B13 evidence."""
import json,hashlib
from pathlib import Path
from collections import Counter
import cadquery as cq
from geometry_core.xcaf import read_xcaf_source
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/evidence/B13/survey';out.mkdir(parents=True,exist_ok=True)
records=[]
for name in ['real-gearbox','real-thruster','satellite-assembly']:
 path=ROOT.parent/'dsh-satellite-geometry/cases'/name/'original.step'
 graph=read_xcaf_source(path);nodes=[]
 for node in graph.nodes:
  if not node.is_leaf:continue
  shape=cq.Shape.cast(graph.geometry(node.key).world_shape)
  if len(shape.Solids())!=1:continue
  solid=shape.Solids()[0];faces=solid.Faces();types=Counter(f.geomType() for f in faces)
  b=solid.BoundingBox()
  nodes.append(dict(key=node.key,name=node.occurrence_name,definition=node.definition_name,faces=len(faces),types=dict(types),volume_mm3=solid.Volume(),area_mm2=solid.Area(),bounds_mm=[b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax],vertices=len(solid.Vertices()),valid=solid.isValid()))
 data=dict(source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,leaves=sum(n.is_leaf for n in graph.nodes),solids=nodes)
 (out/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 records.append(dict(name=name,leaves=data['leaves'],single_solids=len(nodes),types=dict(sum((Counter(x['types']) for x in nodes),Counter())),smallest=sorted(nodes,key=lambda x:x['faces'])[:18]))
 print(json.dumps(records[-1]),flush=True)
