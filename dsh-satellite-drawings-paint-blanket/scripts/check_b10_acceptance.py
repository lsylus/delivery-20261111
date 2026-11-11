import json,sys,tempfile,hashlib,importlib.metadata
from pathlib import Path
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from workflow import exercise
out=ROOT/'docs/evidence/B10';out.mkdir(parents=True,exist_ok=True)
artifacts=out/'artifacts';artifacts.mkdir(exist_ok=True)
directory=Path(tempfile.mkdtemp(prefix='b10-acceptance-',dir=ROOT/'work'))
result=exercise(directory,artifacts)
assert not directory.exists()
manufacturing=cq.Shape.importBrep(str(artifacts/'generated/manufacturing.brep'))
evaluation=cq.Shape.importBrep(str(artifacts/'generated/evaluation.brep'))
baseline=cq.Shape.importBrep(str(artifacts/'generated/baseline.brep'))
assert len(manufacturing.Faces())==5 and len(manufacturing.Solids())==0
assert len(evaluation.Solids())==1 and evaluation.isValid()
assert abs(evaluation.Volume()/baseline.Volume()-1.157625)<1e-12
result.update(manufacturing_faces=len(manufacturing.Faces()),baseline_volume_mm3=baseline.Volume(),cover_volume_mm3=evaluation.Volume(),ratio=evaluation.Volume()/baseline.Volume(),
              environment={p:importlib.metadata.version(p) for p in ('cadquery','cadquery-ocp','pytest','thermal-drawings-service')},
              artifacts=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(artifacts.rglob('*')) if p.is_file()])
(out/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
