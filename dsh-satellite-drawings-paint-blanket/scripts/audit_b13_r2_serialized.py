"""Read serialized R2 artifacts using the unchanged independent R1 audit."""
import os,json,hashlib,importlib.util,copy
from pathlib import Path
import cadquery as cq
import ezdxf
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'docs/evidence/B13/r1-review/independent_geometry.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='12f5cc4610127dc4d78685ee7019431816bf91298a425b6c37f61ac4f4fc7e9c'
spec=importlib.util.spec_from_file_location('independent',source);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r2/http-development');base=out/'r2-http';records=[]
for name in ['fuel-tank','fuel-tank-atlas']:
 initial=audit.load_net(base/(name+'-initial-net.json'));restored=audit.load_net(base/(name+'-restored-net.json'));native=base/(name+'-native')
 panels={p['key']:cq.Shape.importBrep(str(native/Path(p['surface_ref']).name)) for p in initial['panels']}
 value=dict(case=name,tabs=[audit.audit_tab(f,list(panels.values())) for f in cq.Shape.importBrep(str(native/'folded-tabs.brep')).Faces()],initial=audit.drawing_cut_audit(initial),restored=audit.drawing_cut_audit(restored),points=audit.fixed_point_audit(restored,panels),dxf={})
 for suffix in ['drawing.dxf','drawing.readback.dxf']:
  doc=ezdxf.readfile(base/(name+'-export')/suffix);assert doc.units==4
  entities=[]
  for e in doc.modelspace():
   if e.dxf.layer!='CUT':continue
   assert e.dxftype()=='LINE'
   entities.append(dict(layer='CUT',kind='line',start=list(e.dxf.start)[:2],end=list(e.dxf.end)[:2]))
  net=copy.deepcopy(restored);net['drawing_document']['entities']=entities;value['dxf'][suffix]=audit.drawing_cut_audit(net)
 for check in [value['initial'],value['restored'],*value['dxf'].values()]:assert check['complete'] and all(p['components']==1 for p in check['piece_components'])
 records.append(value)
computer=audit.orthogonal_plan_audit(audit.load_net(base/'computer-space-restored-net.json'));assert computer['status']=='pass'
result=dict(status='pass',method='Unchanged independent geometry audit functions applied by execution agent to serialized R2 BRep, NetResult, DXF and real DWG reverse-converted DXF; not independent review approval',sphere_cases=records,computer_space=computer,independent_script_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
(out/'serialized-audit.json').write_text(json.dumps(result,indent=2)+'\n');print('Serialized geometry, connected material and CUT readback: pass')
