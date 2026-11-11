import json
from pathlib import Path
import cadquery as cq
from thermal_drawings.blanket.exterior import scaled_candidate
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/evidence/B13/exterior';out.mkdir(parents=True,exist_ok=True)
for name in ['motor','mounting-plate','fuel-tank','conical-support','launch-mechanism']:
 try:
  source=cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{name}.brep'))
  baseline,cover,record=scaled_candidate(source)
  baseline.exportBrep(str(out/(name+'-baseline.brep')));cover.exportBrep(str(out/(name+'-cover.brep')))
  (out/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
  print(name,record['baseline_volume_mm3'],record['ratio'],record['containment'],len(record['closure']['closed_mouths']),flush=True)
 except Exception as e:
  (out/(name+'.json')).write_text(json.dumps(dict(status='blocked',error=str(e)))+'\n');print(name,type(e).__name__,str(e),flush=True)
