"""Archive real HTTP/worker artifacts and verify native geometry and editable DXF."""
import json,sys,tempfile,hashlib,importlib.metadata
from pathlib import Path
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from net_workflow import exercise
from net_helpers import cover,cut_settings
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.dxf_export import DrawingExporter
out=ROOT/'docs/evidence/B11';out.mkdir(parents=True,exist_ok=True)
artifacts=out/'artifacts';artifacts.mkdir(exist_ok=True)
directory=Path(tempfile.mkdtemp(prefix='b11-acceptance-',dir=ROOT/'work'))
result=exercise(directory,artifacts);assert not directory.exists()
n=json.loads((artifacts/'cross/blanket-net.json').read_text())
body=cq.Shape.importBrep(str(artifacts/'cross/folded-body.brep'));flat=cq.Shape.importBrep(str(artifacts/'cross/flat-body.brep'));tabs=cq.Shape.importBrep(str(artifacts/'cross/folded-tabs.brep'))
assert len(body.Faces())==5 and len(body.Solids())==0 and body.isValid()
assert abs(body.Area()-55125)<1e-6 and abs(flat.Area()-55125)<1e-6 and abs(tabs.Area()-6300)<1e-6
baseline=cq.Shape.importBrep(str(artifacts/'cross/baseline.brep'));evaluation=cq.Shape.importBrep(str(artifacts/'cross/evaluation.brep'))
assert abs(evaluation.Volume()/baseline.Volume()-1.157625)<1e-12
# Explicit native multi-piece and real-hole foldback, also read back from BRep.
for name,dims,hole,multi in [('rectangular',(80,120,60),False,False),('multi-hole',(80,120,60),True,True)]:
    case=artifacts/name;case.mkdir(exist_ok=True);c=cover(dims,hole)
    net=generate_net(c,cut_settings(c) if multi else None,output=case);assert net['status']=='passed'
    shape=cq.Shape.importBrep(str(case/'folded-body.brep'));assert shape.isValid() and abs(shape.Area()-net['areas']['body_mm2'])<1e-6
DrawingExporter().write_dxf(DrawingDocument(n['drawing_document']),artifacts/'cross-net.dxf')
import ezdxf
doc=ezdxf.readfile(artifacts/'cross-net.dxf');assert not doc.audit().has_errors
assert len(doc.modelspace().query('DIMENSION'))>0 and len(doc.modelspace().query('LINE'))>0
result.update(body_faces=len(body.Faces()),body_area_mm2=body.Area(),tab_area_mm2=tabs.Area(),enclosed_volume_mm3=evaluation.Volume(),
              environment={p:importlib.metadata.version(p) for p in ('cadquery','cadquery-ocp','shapely','pytest','ezdxf')},
              artifacts=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(artifacts.rglob('*')) if p.is_file()])
(out/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
