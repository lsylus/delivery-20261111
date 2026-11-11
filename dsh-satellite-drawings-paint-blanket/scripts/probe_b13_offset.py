import json,time
from pathlib import Path
import cadquery as cq
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.BRepOffset import BRepOffset_Skin
from OCP.GeomAbs import GeomAbs_Intersection,GeomAbs_Arc
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from thermal_drawings.blanket.checks import boolean
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'docs/evidence/B13/exterior'
base=cq.Shape.importBrep(str(out/'motor-baseline.brep'))
source=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
for name,join in [('intersection',GeomAbs_Intersection),('arc',GeomAbs_Arc)]:
 start=time.monotonic()
 try:
  op=BRepOffsetAPI_MakeOffsetShape();op.PerformByJoin(base.wrapped,1.0,1e-6,BRepOffset_Skin,False,False,join,True)
  assert op.IsDone();cover=cq.Shape.cast(op.Shape());assert cover.isValid()
  outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,source,cover).Solids())
  record=dict(method=name,status='measured',offset_mm=1.,volume_ratio=cover.Volume()/base.Volume(),outside_volume_mm3=outside,faces=len(cover.Faces()),elapsed_s=time.monotonic()-start)
  cover.exportBrep(str(out/f'motor-offset-{name}.brep'))
 except Exception as e:record=dict(method=name,status='failed',error=str(e),elapsed_s=time.monotonic()-start)
 (out/f'motor-offset-{name}.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
